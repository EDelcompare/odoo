# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


# Namespace del SAT Guatemala
NS_SAT = 'http://www.sat.gob.gt/dte/fel/0.2.0'
NS = {'dte': NS_SAT}

# Tipos de documento FEL reconocidos
TIPOS_DOCUMENTO = [
    ('FACT',         'Factura (FACT)'),
    ('FPEQ',         'Pequeño Contribuyente (FPEQ)'),
    ('RDON',         'Donación / Exento (RDON)'),
    ('FCAM',         'Factura Cambiaria (FCAM)'),
    ('NABN',         'Nota de Abono (NABN)'),
    ('NCRE',         'Nota de Crédito (NCRE)'),
    ('NDEB',         'Nota de Débito (NDEB)'),
    ('anulada',      'Factura Anulada'),
    ('otro',         'Otro Documento'),
]

# FCAM (Factura Cambiaria) es una factura normal de régimen general -
# solo trae un complemento de abonos/plazos de pago, no reduce el total.
# NABN (Nota de Abono) es el acuse de un abono a una Factura Cambiaria,
# no una compra nueva: se deja como 'otro' para revisión manual.
# Los únicos tipos que realmente son nota de crédito/débito son NCRE y NDEB.
TIPOS_NOTA_CREDITO = {'NCRE', 'NDEB'}

# Tipos que se contabilizan como factura normal (régimen general)
TIPOS_FACTURA_NORMAL = {'FACT', 'FPEQ', 'RDON', 'FCAM'}

# Tipo de bien/servicio
BIEN_O_SERVICIO = [
    ('B', 'Bien'),
    ('S', 'Servicio'),
    ('M', 'Mixto (Bien y Servicio)'),
]


class GtPolizaCompraLinea(models.Model):
    """
    Línea de Póliza de Compras — representa UNA factura FEL.

    Cada línea genera su propio asiento contable (account.move)
    para aparecer individualmente en el Libro de Compras.
    """
    _name = 'gt.poliza.compra.linea'
    _description = 'Línea de Póliza de Compras FEL'
    _order = 'fecha_emision, id'

    # ── Póliza padre ──────────────────────────────────────────────────────────
    poliza_id = fields.Many2one(
        'gt.poliza.compra', string='Póliza',
        required=True, ondelete='cascade', index=True)

    company_id = fields.Many2one(
        related='poliza_id.company_id', store=True, readonly=True)

    currency_id = fields.Many2one(
        related='poliza_id.currency_id', store=True, readonly=True)

    # ── Tipo de documento ────────────────────────────────────────────────────
    tipo_documento = fields.Selection(
        TIPOS_DOCUMENTO,
        string='Tipo de Documento',
        required=True, default='FACT',
        help="Tipo de documento FEL según SAT Guatemala.")

    es_nota_credito = fields.Boolean(
        string='Es Nota de Crédito',
        compute='_compute_flags', store=True)

    es_anulada = fields.Boolean(
        string='Es Anulada',
        compute='_compute_flags', store=True)

    es_exenta = fields.Boolean(
        string='Es Exenta / Donación',
        compute='_compute_flags', store=True)

    es_pequeno_contribuyente = fields.Boolean(
        string='Es Pequeño Contribuyente',
        compute='_compute_flags', store=True)

    tiene_idp = fields.Boolean(
        string='Tiene IDP (Combustible)',
        help="Detectado automáticamente si el XML contiene impuesto PETROLEO.")

    # ── Datos del emisor (del XML SAT) ────────────────────────────────────────
    nit_emisor = fields.Char(string='NIT Emisor', required=True)
    nombre_emisor = fields.Char(string='Nombre Emisor', required=True)
    nombre_comercial = fields.Char(string='Nombre Comercial')
    afiliacion_iva = fields.Char(
        string='Afiliación IVA',
        help="GEN = Régimen General, PEQ = Pequeño Contribuyente")

    proveedor_id = fields.Many2one(
        'res.partner', string='Proveedor en Odoo',
        help="Vinculado automáticamente por NIT. Si no existe se crea.")

    # ── Datos del documento ───────────────────────────────────────────────────
    uuid = fields.Char(
        string='UUID / No. Autorización',
        help="Número de autorización único del SAT. Previene duplicados.")

    serie = fields.Char(string='Serie')
    numero_documento = fields.Char(string='No. Documento')
    fecha_emision = fields.Datetime(string='Fecha y Hora Emisión')
    fecha = fields.Date(
        string='Fecha',
        compute='_compute_fecha', store=True)

    # ── Tipo de bien/servicio ─────────────────────────────────────────────────
    bien_o_servicio = fields.Selection(
        BIEN_O_SERVICIO,
        string='Bien o Servicio',
        default='S',
        help="Detectado del XML. Editable si hay líneas mixtas.")

    # ── Montos (columnas del Libro de Compras) ────────────────────────────────
    monto_bienes = fields.Monetary(
        string='Bienes', currency_field='currency_id')

    monto_servicios = fields.Monetary(
        string='Servicios', currency_field='currency_id')

    monto_combustible = fields.Monetary(
        string='Combustible', currency_field='currency_id')

    monto_pequeno_contribuyente = fields.Monetary(
        string='Pequeño Contribuyente', currency_field='currency_id')

    monto_exento = fields.Monetary(
        string='Exento', currency_field='currency_id')

    monto_iva = fields.Monetary(
        string='IVA Crédito Fiscal', currency_field='currency_id')

    monto_idp = fields.Monetary(
        string='IDP Combustible', currency_field='currency_id')

    venta_neta = fields.Monetary(
        string='Venta Neta', currency_field='currency_id',
        compute='_compute_venta_neta', store=True)

    gran_total = fields.Monetary(
        string='Total', currency_field='currency_id')

    # ── Cuenta contable de gasto ──────────────────────────────────────────────
    cuenta_gasto_id = fields.Many2one(
        'account.account', string='Cuenta de Gasto',
        domain=[('account_type', 'like', 'expense')],
        help="Única campo que el usuario debe seleccionar manualmente.")

    descripcion_gasto = fields.Char(
        string='Descripción del Gasto',
        help="Descripción para el asiento contable.")

    # ── Asiento generado ──────────────────────────────────────────────────────
    move_id = fields.Many2one(
        'account.move', string='Asiento Contable',
        readonly=True, copy=False)

    move_state = fields.Selection(
        related='move_id.state', string='Estado Asiento', readonly=True)

    # ── XML original almacenado ───────────────────────────────────────────────
    xml_original = fields.Text(
        string='XML Original SAT',
        help="Contenido del XML original para referencia y auditoría.")

    # ═════════════════════════════════════════════════════════════════════════
    # Cómputos
    # ═════════════════════════════════════════════════════════════════════════

    @api.depends('tipo_documento')
    def _compute_flags(self):
        for l in self:
            l.es_nota_credito         = l.tipo_documento in TIPOS_NOTA_CREDITO
            l.es_anulada              = l.tipo_documento == 'anulada'
            l.es_exenta               = l.tipo_documento == 'RDON'
            l.es_pequeno_contribuyente = l.tipo_documento == 'FPEQ'

    @api.depends('fecha_emision')
    def _compute_fecha(self):
        for l in self:
            l.fecha = l.fecha_emision.date() if l.fecha_emision else False

    @api.depends('monto_bienes', 'monto_servicios', 'monto_combustible',
                 'monto_pequeno_contribuyente', 'monto_exento')
    def _compute_venta_neta(self):
        for l in self:
            l.venta_neta = (l.monto_bienes + l.monto_servicios +
                           l.monto_combustible + l.monto_pequeno_contribuyente +
                           l.monto_exento)

    # ═════════════════════════════════════════════════════════════════════════
    # Validaciones
    # ═════════════════════════════════════════════════════════════════════════

    @api.constrains('uuid')
    def _check_uuid_duplicado(self):
        """El UUID debe ser único — previene importar la misma factura dos veces."""
        for linea in self:
            if not linea.uuid:
                continue
            duplicado = self.search([
                ('uuid', '=', linea.uuid),
                ('id', '!=', linea.id),
            ], limit=1)
            if duplicado:
                raise ValidationError(_(
                    'La factura con UUID %s ya existe en la Póliza %s.\n'
                    'No se puede registrar la misma factura dos veces.'
                ) % (linea.uuid, duplicado.poliza_id.name))

    # ═════════════════════════════════════════════════════════════════════════
    # Parser XML del SAT
    # ═════════════════════════════════════════════════════════════════════════

    @api.model
    def _parsear_xml_sat(self, xml_content):
        """
        Parsea un XML FEL del SAT Guatemala y retorna un dict con los datos.
        Valida que sea un DTE guatemalteco correcto.
        Detecta automáticamente: tipo documento, IDP, bien/servicio.
        """
        import xml.etree.ElementTree as ET
        from datetime import datetime, timezone

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise UserError(_('El archivo no es un XML válido: %s') % str(e))

        # Validar que sea un DTE guatemalteco
        if NS_SAT not in root.tag and not root.find('.//dte:DTE', NS) and \
           not root.find('.//{%s}DTE' % NS_SAT):
            raise UserError(_(
                'El archivo no es un DTE guatemalteco válido.\n'
                'Solo se aceptan archivos XML del SAT de Guatemala.'))

        # Extraer secciones principales
        datos_generales  = root.find('.//{%s}DatosGenerales' % NS_SAT)
        emisor           = root.find('.//{%s}Emisor' % NS_SAT)
        receptor         = root.find('.//{%s}Receptor' % NS_SAT)
        items            = root.findall('.//{%s}Item' % NS_SAT)
        totales          = root.find('.//{%s}Totales' % NS_SAT)
        certificacion    = root.find('.//{%s}Certificacion' % NS_SAT)
        num_autorizacion = root.find('.//{%s}NumeroAutorizacion' % NS_SAT)

        if datos_generales is None or emisor is None or num_autorizacion is None:
            raise UserError(_(
                'El XML no contiene los elementos obligatorios de un DTE '
                '(DatosGenerales, Emisor, NumeroAutorizacion).'))

        # Tipo de documento
        tipo_raw = datos_generales.get('Tipo', 'FACT')
        if tipo_raw in TIPOS_NOTA_CREDITO:
            tipo_doc = tipo_raw
        elif tipo_raw in TIPOS_FACTURA_NORMAL:
            tipo_doc = tipo_raw
        else:
            tipo_doc = 'otro'

        # Fecha emisión
        fecha_str = datos_generales.get('FechaHoraEmision', '')
        try:
            fecha_emision = datetime.fromisoformat(fecha_str)
            if fecha_emision.tzinfo is not None:
                fecha_emision = fecha_emision.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            fecha_emision = False

        # ── Análisis de líneas (items) ────────────────────────────────────────
        # Cada item se clasifica por separado: si no trae impuesto IVA se
        # considera exento (igual que se aísla el IDP), en vez de asumir
        # que toda la factura comparte una sola clasificación.
        tiene_idp        = False
        tiene_bienes     = False
        tiene_servicios  = False
        monto_petroleo   = 0.0

        monto_bienes_item      = 0.0
        monto_servicios_item   = 0.0
        monto_combustible_item = 0.0
        monto_exento_item      = 0.0

        for item in items:
            bs = item.get('BienOServicio', 'S')
            if bs == 'B':
                tiene_bienes = True
            elif bs == 'S':
                tiene_servicios = True

            try:
                item_total = float(item.find('{%s}Total' % NS_SAT).text or 0)
            except (AttributeError, ValueError, TypeError):
                item_total = 0.0

            item_iva = 0.0
            item_petroleo = 0.0

            for impuesto in item.findall('.//{%s}Impuesto' % NS_SAT):
                nombre_imp = impuesto.find('{%s}NombreCorto' % NS_SAT)
                if nombre_imp is None or not nombre_imp.text:
                    continue
                monto_imp_el = impuesto.find('{%s}MontoImpuesto' % NS_SAT)
                try:
                    monto_imp_val = float(monto_imp_el.text or 0) if monto_imp_el is not None else 0.0
                except (ValueError, TypeError):
                    monto_imp_val = 0.0

                if nombre_imp.text == 'IVA':
                    item_iva += monto_imp_val
                elif nombre_imp.text == 'PETROLEO':
                    item_petroleo += monto_imp_val
                    tiene_idp = True
                # Cualquier otro impuesto (ej. TURISMO HOSPEDAJE) no tiene
                # columna propia en el Libro de Compras: se queda dentro de
                # la base para que la factura no quede descuadrada.

            monto_petroleo += item_petroleo

            if item_petroleo:
                # Combustible: base sin IVA ni IDP (cualquier otro impuesto
                # del item se queda incluido en esta base)
                base_item = round(item_total - item_iva - item_petroleo, 2)
                monto_combustible_item += base_item
            elif item_iva:
                # Bien o servicio gravado con IVA (otros impuestos del item
                # quedan incluidos en esta base)
                base_item = round(item_total - item_iva, 2)
                if bs == 'B':
                    monto_bienes_item += base_item
                else:
                    monto_servicios_item += base_item
            else:
                # Sin impuesto IVA en el item: exento
                monto_exento_item += item_total

        # Bien o Servicio de la factura completa (solo informativo)
        if tiene_bienes and tiene_servicios:
            bien_o_servicio = 'M'
        elif tiene_bienes:
            bien_o_servicio = 'B'
        else:
            bien_o_servicio = 'S'

        # ── Totales ───────────────────────────────────────────────────────────
        gran_total = 0.0
        monto_iva  = 0.0
        if totales is not None:
            gt_el = totales.find('{%s}GranTotal' % NS_SAT)
            if gt_el is not None:
                try:
                    gran_total = float(gt_el.text or 0)
                except (ValueError, TypeError):
                    pass
            for ti in totales.findall('.//{%s}TotalImpuesto' % NS_SAT):
                nombre = ti.get('NombreCorto', '')
                monto  = ti.get('TotalMontoImpuesto', '0')
                if nombre == 'IVA':
                    try:
                        monto_iva = float(monto)
                    except (ValueError, TypeError):
                        pass

        # ── Calcular columnas del Libro de Compras ────────────────────────────
        monto_bienes                = 0.0
        monto_servicios             = 0.0
        monto_combustible           = 0.0
        monto_pequeno_contribuyente = 0.0
        monto_exento                = 0.0
        iva_credito                 = 0.0

        if tipo_doc == 'anulada':
            pass  # Todo en cero

        elif tipo_doc == 'FPEQ':
            # Pequeño contribuyente: todo el documento va en una sola
            # columna, sin crédito de IVA, sin importar el detalle por item.
            monto_pequeno_contribuyente = gran_total

        elif tipo_doc == 'RDON':
            # Donación: todo el documento es exento, sin importar el detalle.
            monto_exento = gran_total

        else:
            # Régimen general (FACT, FCAM, otro): clasificación por item,
            # así una factura mixta reparte cada renglón a su columna real
            # (bienes / servicios / combustible / exento) en vez de asumir
            # que toda la factura es de un solo tipo.
            monto_bienes      = round(monto_bienes_item, 2)
            monto_servicios   = round(monto_servicios_item, 2)
            monto_combustible = round(monto_combustible_item, 2)
            monto_exento      = round(monto_exento_item, 2)
            if tipo_doc in ('FACT', 'FCAM'):
                iva_credito = monto_iva

        # ── Resultado ─────────────────────────────────────────────────────────
        return {
            'tipo_documento':              tipo_doc,
            'nit_emisor':                  emisor.get('NITEmisor', ''),
            'nombre_emisor':               emisor.get('NombreEmisor', ''),
            'nombre_comercial':            emisor.get('NombreComercial', ''),
            'afiliacion_iva':              emisor.get('AfiliacionIVA', ''),
            'uuid':                        num_autorizacion.text or '',
            'serie':                       num_autorizacion.get('Serie', ''),
            'numero_documento':            num_autorizacion.get('Numero', ''),
            'fecha_emision':               fecha_emision,
            'bien_o_servicio':             bien_o_servicio,
            'tiene_idp':                   tiene_idp,
            'monto_bienes':                monto_bienes,
            'monto_servicios':             monto_servicios,
            'monto_combustible':           monto_combustible,
            'monto_pequeno_contribuyente': monto_pequeno_contribuyente,
            'monto_exento':                monto_exento,
            'monto_iva':                   iva_credito,
            'monto_idp':                   monto_petroleo,
            'gran_total':                  gran_total,
            'descripcion_gasto':           emisor.get('NombreComercial') or emisor.get('NombreEmisor', ''),
        }

    # ═════════════════════════════════════════════════════════════════════════
    # Generación de asientos contables
    # ═════════════════════════════════════════════════════════════════════════

    def _get_o_crear_proveedor(self):
        """Busca el proveedor por NIT. Si no existe lo crea."""
        self.ensure_one()
        partner = self.env['res.partner'].search([
            ('vat', '=', self.nit_emisor),
            ('is_company', '=', True),
        ], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name':         self.nombre_comercial or self.nombre_emisor,
                'vat':          self.nit_emisor,
                'company_type': 'company',
                'is_company':   True,
                'supplier_rank': 1,
                'comment': _('Creado automáticamente desde importación FEL SAT'),
            })
        self.proveedor_id = partner
        return partner

    def _generar_asiento_normal(self):
        """
        Genera asiento para FACT, FPEQ, RDON.

        DEBE:   Gasto (cuenta 6)
                IVA por cobrar (cuenta 1)      ← solo si aplica
                IDP Combustible (cuenta 6)     ← solo si tiene IDP
        HABER:  Proveedores (cuenta 2)
        """
        self.ensure_one()
        partner = self._get_o_crear_proveedor()
        poliza  = self.poliza_id

        # Obtener cuentas configuradas
        config  = self.env['gt.compras.config'].sudo()._get_config(poliza.company_id)
        cuenta_iva        = config.cuenta_iva_id
        cuenta_proveedores = config.cuenta_proveedores_id
        cuenta_idp        = config.cuenta_idp_id

        if not self.cuenta_gasto_id:
            raise UserError(_(
                'La factura de %s no tiene cuenta de gasto asignada.'
            ) % self.nombre_emisor)

        ref = '%s | %s | Serie: %s No: %s | UUID: %s' % (
            poliza.name, self.nombre_emisor,
            self.serie, self.numero_documento,
            self.uuid)

        lineas_asiento = []

        # Línea de gasto principal
        monto_gasto = (self.monto_bienes + self.monto_servicios +
                      self.monto_combustible + self.monto_pequeno_contribuyente +
                      self.monto_exento)
        if monto_gasto:
            lineas_asiento.append((0, 0, {
                'account_id': self.cuenta_gasto_id.id,
                'name':       self.descripcion_gasto or self.nombre_emisor,
                'quantity':   1,
                'price_unit': monto_gasto,
                'tax_ids':    [(6, 0, [])],
            }))

        # Línea IVA por cobrar (solo FACT régimen general)
        if self.monto_iva and self.tipo_documento in ('FACT', 'FCAM'):
            if not cuenta_iva:
                raise UserError(_('Configure la cuenta de IVA por Cobrar en Configuración GT.'))
            lineas_asiento.append((0, 0, {
                'account_id': cuenta_iva.id,
                'name':       _('IVA por Cobrar - %s') % self.nombre_emisor,
                'quantity':   1,
                'price_unit': self.monto_iva,
                'tax_ids':    [(6, 0, [])],
            }))

        # Línea IDP combustible
        if self.monto_idp and self.tiene_idp:
            if not cuenta_idp:
                raise UserError(_('Configure la cuenta de IDP en Configuración GT.'))
            lineas_asiento.append((0, 0, {
                'account_id': cuenta_idp.id,
                'name':       _('IDP Combustible - %s') % self.nombre_emisor,
                'quantity':   1,
                'price_unit': self.monto_idp,
                'tax_ids':    [(6, 0, [])],
            }))

        # Línea proveedores (crédito total)
        if not cuenta_proveedores:
            raise UserError(_('Configure la cuenta de Proveedores en Configuración GT.'))
        lineas_asiento.append((0, 0, {
            'account_id': cuenta_proveedores.id,
            'name':       _('Por pagar - %s') % self.nombre_emisor,
            'balance':    -self.gran_total,
        }))

        move_vals = {
            'move_type':        'in_invoice',
            'partner_id':       partner.id,
            'invoice_date':     self.fecha,
            'ref':              ref,
            'journal_id':       poliza.journal_id.id,
            'gt_poliza_id':     poliza.id,
            'line_ids':         lineas_asiento,
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.move_id = move

    def _generar_asiento_anulada(self):
        """Factura anulada: se registra con monto cero para trazabilidad."""
        self.ensure_one()
        partner = self._get_o_crear_proveedor()
        poliza  = self.poliza_id
        ref = '[ANULADA] %s | %s | UUID: %s' % (
            poliza.name, self.nombre_emisor, self.uuid)
        # Asiento en cero — solo para que aparezca en el Libro de Compras
        move_vals = {
            'move_type':    'in_invoice',
            'partner_id':   partner.id,
            'invoice_date': self.fecha,
            'ref':          ref,
            'journal_id':   poliza.journal_id.id,
            'gt_poliza_id': poliza.id,
            'line_ids': [(0, 0, {
                'account_id': self.cuenta_gasto_id.id if self.cuenta_gasto_id
                              else self.env['account.account'].search([
                                  ('account_type', 'like', 'expense'),
                                  ('company_id', '=', self.company_id.id)
                              ], limit=1).id,
                'name': _('FACTURA ANULADA - %s') % self.nombre_emisor,
                'balance': 0.0,
            })],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.move_id = move

    def _generar_asiento_nota_credito(self):
        """Nota de crédito: genera in_refund (resta del total)."""
        self.ensure_one()
        partner = self._get_o_crear_proveedor()
        poliza  = self.poliza_id
        config  = self.env['gt.compras.config'].sudo()._get_config(poliza.company_id)

        if not config.cuenta_proveedores_id:
            raise UserError(_('Configure la cuenta de Proveedores en Configuración GT.'))

        ref = '[NOTA CRÉDITO] %s | %s | UUID: %s' % (
            poliza.name, self.nombre_emisor, self.uuid)
        move_vals = {
            'move_type':    'in_refund',
            'partner_id':   partner.id,
            'invoice_date': self.fecha,
            'ref':          ref,
            'journal_id':   poliza.journal_id.id,
            'gt_poliza_id': poliza.id,
            'line_ids': [
                (0, 0, {
                    'account_id': self.cuenta_gasto_id.id,
                    'name':       _('Nota de Crédito - %s') % self.nombre_emisor,
                    'quantity':   1,
                    'price_unit': self.gran_total,
                    'tax_ids':    [(6, 0, [])],
                }),
                (0, 0, {
                    'account_id': config.cuenta_proveedores_id.id,
                    'name':       _('Nota de Crédito - Por pagar - %s') % self.nombre_emisor,
                    'balance':    self.gran_total,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.move_id = move


# ─── Extensión de account.move para vincular a la póliza ─────────────────────
class AccountMove(models.Model):
    _inherit = 'account.move'

    gt_poliza_id = fields.Many2one(
        'gt.poliza.compra', string='Póliza de Compras GT',
        readonly=True, copy=False, index=True)


# ─── Configuración de cuentas contables ──────────────────────────────────────
class GtComprasConfig(models.Model):
    """Configuración de cuentas contables para el módulo GT Compras FEL."""
    _name = 'gt.compras.config'
    _description = 'Configuración Cuentas GT Compras FEL'

    company_id = fields.Many2one(
        'res.company', string='Empresa',
        required=True, default=lambda self: self.env.company)

    cuenta_iva_id = fields.Many2one(
        'account.account', string='IVA por Cobrar (Cuenta 1)',
        domain=[('account_type', '=', 'asset_current')],
        help="Ej: 1120201 IVA por Cobrar")

    cuenta_proveedores_id = fields.Many2one(
        'account.account', string='Proveedores (Cuenta 2)',
        domain=[('account_type', 'in', ['liability_payable'])],
        help="Ej: Cuenta 2 - Proveedores / Cuentas por Pagar")

    cuenta_idp_id = fields.Many2one(
        'account.account', string='IDP Combustible (Cuenta 6)',
        domain=[('account_type', 'like', 'expense')],
        help="Ej: 6110314 IDP Combustible")

    def _get_config(self, company):
        config = self.search([('company_id', '=', company.id)], limit=1)
        if not config:
            raise UserError(_(
                'Configure las cuentas contables del módulo GT Compras FEL '
                'en: Contabilidad → Configuración → Configuración GT Compras'))
        return config
