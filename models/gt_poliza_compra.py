# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class GtPolizaCompra(models.Model):
    """
    Póliza de Compras Guatemala FEL.

    Documento principal que agrupa una o varias facturas FEL.
    Cada póliza tiene un número de secuencia único e irrepetible.
    Puede cargarse manualmente o mediante importación de XML/ZIP del SAT.
    """
    _name = 'gt.poliza.compra'
    _description = 'Póliza de Compras FEL Guatemala'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, name desc'

    # ── Identificación ────────────────────────────────────────────────────────
    name = fields.Char(
        string='No. Póliza',
        required=True, copy=False, readonly=True,
        default=lambda self: _('Nuevo'),
        tracking=True,
        help="Número de póliza único e irrepetible. Se genera automáticamente.")

    state = fields.Selection([
        ('borrador',   'Borrador'),
        ('confirmado', 'Confirmado'),
        ('cancelado',  'Cancelado'),
    ], string='Estado', default='borrador', required=True,
       tracking=True, copy=False)

    # ── Fechas y período ──────────────────────────────────────────────────────
    fecha = fields.Date(
        string='Fecha de Póliza',
        required=True, default=fields.Date.context_today,
        tracking=True)

    periodo_mes = fields.Selection([
        ('01', 'Enero'), ('02', 'Febrero'), ('03', 'Marzo'),
        ('04', 'Abril'), ('05', 'Mayo'), ('06', 'Junio'),
        ('07', 'Julio'), ('08', 'Agosto'), ('09', 'Septiembre'),
        ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
    ], string='Mes', required=True,
       default=lambda self: fields.Date.today().strftime('%m'))

    periodo_anio = fields.Integer(
        string='Año', required=True,
        default=lambda self: fields.Date.today().year)

    # ── Empresa ───────────────────────────────────────────────────────────────
    company_id = fields.Many2one(
        'res.company', string='Empresa',
        required=True, default=lambda self: self.env.company)

    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id)

    # ── Diario contable ───────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        'account.journal', string='Diario de Compras',
        required=True,
        domain=[('type', '=', 'purchase')],
        default=lambda self: self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.env.company.id)
        ], limit=1))

    # ── Líneas de facturas ────────────────────────────────────────────────────
    linea_ids = fields.One2many(
        'gt.poliza.compra.linea', 'poliza_id',
        string='Facturas / Documentos')

    linea_count = fields.Integer(
        string='# Documentos',
        compute='_compute_totales', store=True)

    # ── Totales del Libro de Compras ──────────────────────────────────────────
    total_bienes = fields.Monetary(
        string='Total Bienes',
        currency_field='currency_id',
        compute='_compute_totales', store=True)

    total_servicios = fields.Monetary(
        string='Total Servicios',
        currency_field='currency_id',
        compute='_compute_totales', store=True)

    total_combustible = fields.Monetary(
        string='Total Combustible',
        currency_field='currency_id',
        compute='_compute_totales', store=True)

    total_pequeno_contribuyente = fields.Monetary(
        string='Total Pequeño Contribuyente',
        currency_field='currency_id',
        compute='_compute_totales', store=True)

    total_exentas = fields.Monetary(
        string='Total Exentas',
        currency_field='currency_id',
        compute='_compute_totales', store=True)

    total_iva = fields.Monetary(
        string='Total IVA Crédito Fiscal',
        currency_field='currency_id',
        compute='_compute_totales', store=True)

    total_idp = fields.Monetary(
        string='Total IDP',
        currency_field='currency_id',
        compute='_compute_totales', store=True)

    gran_total = fields.Monetary(
        string='Gran Total',
        currency_field='currency_id',
        compute='_compute_totales', store=True)

    # ── Notas ─────────────────────────────────────────────────────────────────
    notas = fields.Text(string='Notas / Observaciones')

    # ── Asientos generados ────────────────────────────────────────────────────
    move_ids = fields.One2many(
        'account.move', 'gt_poliza_id',
        string='Asientos Contables')

    move_count = fields.Integer(
        string='# Asientos',
        compute='_compute_move_count')

    # ═════════════════════════════════════════════════════════════════════════
    # Cómputos
    # ═════════════════════════════════════════════════════════════════════════

    @api.depends('linea_ids.monto_bienes', 'linea_ids.monto_servicios',
                 'linea_ids.monto_combustible', 'linea_ids.monto_pequeno_contribuyente',
                 'linea_ids.monto_exento', 'linea_ids.monto_iva',
                 'linea_ids.monto_idp', 'linea_ids.gran_total')
    def _compute_totales(self):
        for p in self:
            lineas = p.linea_ids
            p.linea_count             = len(lineas)
            p.total_bienes            = sum(lineas.mapped('monto_bienes'))
            p.total_servicios         = sum(lineas.mapped('monto_servicios'))
            p.total_combustible       = sum(lineas.mapped('monto_combustible'))
            p.total_pequeno_contribuyente = sum(lineas.mapped('monto_pequeno_contribuyente'))
            p.total_exentas           = sum(lineas.mapped('monto_exento'))
            p.total_iva               = sum(lineas.mapped('monto_iva'))
            p.total_idp               = sum(lineas.mapped('monto_idp'))
            p.gran_total              = sum(lineas.mapped('gran_total'))

    @api.depends('move_ids')
    def _compute_move_count(self):
        for p in self:
            p.move_count = len(p.move_ids)

    # ═════════════════════════════════════════════════════════════════════════
    # Secuencia
    # ═════════════════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'gt.poliza.compra') or _('Nuevo')
        return super().create(vals_list)

    # ═════════════════════════════════════════════════════════════════════════
    # Transiciones
    # ═════════════════════════════════════════════════════════════════════════

    def action_confirmar(self):
        """Confirma la póliza y genera los asientos contables."""
        for poliza in self:
            if poliza.state != 'borrador':
                raise UserError(_('Solo se pueden confirmar pólizas en borrador.'))
            if not poliza.linea_ids:
                raise UserError(_('La póliza no tiene documentos. Cargue al menos una factura.'))
            lineas_sin_cuenta = poliza.linea_ids.filtered(
                lambda l: not l.cuenta_gasto_id and l.tipo_documento != 'anulada')
            if lineas_sin_cuenta:
                raise UserError(_(
                    'Las siguientes líneas no tienen cuenta de gasto asignada:\n%s'
                ) % '\n'.join(lineas_sin_cuenta.mapped('nombre_emisor')))
            poliza._generar_asientos()
            poliza.state = 'confirmado'
            poliza.message_post(
                body=_('Póliza confirmada. %d asiento(s) generado(s).') % poliza.move_count)

    def action_cancelar(self):
        """Cancela la póliza y los asientos generados."""
        for poliza in self:
            if poliza.state == 'cancelado':
                raise UserError(_('La póliza ya está cancelada.'))
            for move in poliza.move_ids.filtered(lambda m: m.state == 'posted'):
                move.button_cancel()
            poliza.state = 'cancelado'

    def action_regresar_borrador(self):
        for poliza in self:
            if poliza.state != 'cancelado':
                raise UserError(_('Solo se pueden regresar a borrador pólizas canceladas.'))
            poliza.state = 'borrador'

    # ═════════════════════════════════════════════════════════════════════════
    # Carga de XML
    # ═════════════════════════════════════════════════════════════════════════

    def action_cargar_xml(self):
        """Abre el wizard de carga de XML / ZIP."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cargar XML del SAT'),
            'res_model': 'gt.wizard.carga.xml',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_poliza_id': self.id},
        }

    def action_ver_asientos(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Asientos Contables'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('gt_poliza_id', '=', self.id)],
        }

    # ═════════════════════════════════════════════════════════════════════════
    # Generación de asientos contables
    # ═════════════════════════════════════════════════════════════════════════

    def _generar_asientos(self):
        """
        Genera UN asiento contable por cada línea (factura) de la póliza.
        Cada factura va individual al Libro de Compras (account.move in_invoice).
        """
        self.ensure_one()
        for linea in self.linea_ids:
            if linea.tipo_documento == 'anulada':
                # Factura anulada: se registra con impacto cero
                linea._generar_asiento_anulada()
            elif linea.es_nota_credito:
                linea._generar_asiento_nota_credito()
            else:
                linea._generar_asiento_normal()

    # ═════════════════════════════════════════════════════════════════════════
    # Reporte
    # ═════════════════════════════════════════════════════════════════════════

    def action_imprimir_libro_compras(self):
        return self.env.ref(
            'gt_compras_fel.action_reporte_libro_compras').report_action(self)
