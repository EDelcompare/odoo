# -*- coding: utf-8 -*-
import base64
import zipfile
import io
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class GtWizardCargaXml(models.TransientModel):
    """
    Wizard para cargar archivos XML o ZIP del SAT Guatemala.
    Permite cargar un XML individual o un ZIP con múltiples XML.
    """
    _name = 'gt.wizard.carga.xml'
    _description = 'Carga de XML FEL del SAT Guatemala'

    poliza_id = fields.Many2one(
        'gt.poliza.compra', string='Póliza de Compras',
        required=True)

    modo_carga = fields.Selection([
        ('xml', 'Un archivo XML'),
        ('zip', 'ZIP con múltiples XML'),
    ], string='Modo de Carga', required=True, default='xml')

    archivo = fields.Binary(
        string='Archivo XML o ZIP',
        required=True,
        help="Seleccione el archivo XML del SAT o un ZIP con múltiples XML.")

    nombre_archivo = fields.Char(string='Nombre del Archivo')

    # ── Resultado de la carga ─────────────────────────────────────────────────
    resultado_ids = fields.One2many(
        'gt.wizard.carga.xml.resultado', 'wizard_id',
        string='Resultado de la Carga')

    estado_carga = fields.Selection([
        ('pendiente',  'Pendiente'),
        ('procesado',  'Procesado'),
    ], default='pendiente')

    total_cargados   = fields.Integer(string='Cargados', readonly=True)
    total_duplicados = fields.Integer(string='Duplicados', readonly=True)
    total_errores    = fields.Integer(string='Errores', readonly=True)

    @api.onchange('nombre_archivo')
    def _onchange_nombre_archivo(self):
        """Detecta automáticamente el modo según la extensión del archivo."""
        if self.nombre_archivo:
            if self.nombre_archivo.lower().endswith('.zip'):
                self.modo_carga = 'zip'
            elif self.nombre_archivo.lower().endswith('.xml'):
                self.modo_carga = 'xml'

    def action_procesar(self):
        """Procesa el archivo y carga las facturas a la póliza."""
        self.ensure_one()
        if not self.archivo:
            raise UserError(_('Seleccione un archivo para cargar.'))

        contenido = base64.b64decode(self.archivo)
        linea_model = self.env['gt.poliza.compra.linea']

        archivos_xml = []  # lista de (nombre, contenido_xml)

        if self.modo_carga == 'zip':
            # Descomprimir ZIP y extraer todos los XML
            try:
                with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
                    for nombre in zf.namelist():
                        if nombre.lower().endswith('.xml'):
                            xml_bytes = zf.read(nombre)
                            archivos_xml.append((nombre, xml_bytes))
            except zipfile.BadZipFile:
                raise UserError(_(
                    'El archivo no es un ZIP válido. '
                    'Verifique que sea el ZIP descargado del SAT.'))
            if not archivos_xml:
                raise UserError(_('El ZIP no contiene archivos XML.'))
        else:
            # XML individual
            nombre = self.nombre_archivo or 'archivo.xml'
            archivos_xml.append((nombre, contenido))

        # ── Procesar cada XML ─────────────────────────────────────────────────
        cargados   = 0
        duplicados = 0
        errores    = 0
        resultados = []

        for nombre_xml, xml_content in archivos_xml:
            try:
                # Parsear XML
                datos = linea_model._parsear_xml_sat(xml_content.decode('utf-8'))

                # Verificar duplicado por UUID
                uuid = datos.get('uuid', '')
                if uuid:
                    existe = linea_model.search([('uuid', '=', uuid)], limit=1)
                    if existe:
                        duplicados += 1
                        resultados.append({
                            'nombre_archivo': nombre_xml,
                            'estado':        'duplicado',
                            'mensaje':       _('UUID ya existe en póliza %s') % existe.poliza_id.name,
                            'uuid':          uuid,
                        })
                        continue

                # Crear la línea en la póliza
                datos['poliza_id'] = self.poliza_id.id
                datos['xml_original'] = xml_content.decode('utf-8')
                linea_model.create(datos)
                cargados += 1
                resultados.append({
                    'nombre_archivo': nombre_xml,
                    'estado':        'ok',
                    'mensaje':       _('Cargado correctamente'),
                    'uuid':          uuid,
                })

            except UserError as e:
                errores += 1
                resultados.append({
                    'nombre_archivo': nombre_xml,
                    'estado':        'error',
                    'mensaje':       str(e),
                    'uuid':          '',
                })
            except Exception as e:
                errores += 1
                resultados.append({
                    'nombre_archivo': nombre_xml,
                    'estado':        'error',
                    'mensaje':       _('Error inesperado: %s') % str(e),
                    'uuid':          '',
                })

        # ── Guardar resultados ────────────────────────────────────────────────
        self.estado_carga    = 'procesado'
        self.total_cargados  = cargados
        self.total_duplicados = duplicados
        self.total_errores   = errores

        for r in resultados:
            r['wizard_id'] = self.id
        self.env['gt.wizard.carga.xml.resultado'].create(resultados)

        # Mensaje en la póliza
        self.poliza_id.message_post(body=_(
            'Carga XML completada: %d cargados, %d duplicados, %d errores.'
        ) % (cargados, duplicados, errores))

        # Reabrir el wizard mostrando resultados
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'gt.wizard.carga.xml',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_cerrar(self):
        return {'type': 'ir.actions.act_window_close'}


class GtWizardCargaXmlResultado(models.TransientModel):
    """Resultado línea por línea de la carga de XML."""
    _name = 'gt.wizard.carga.xml.resultado'
    _description = 'Resultado de Carga XML'

    wizard_id = fields.Many2one('gt.wizard.carga.xml', ondelete='cascade')

    nombre_archivo = fields.Char(string='Archivo')
    uuid           = fields.Char(string='UUID')
    estado         = fields.Selection([
        ('ok',         'Cargado'),
        ('duplicado',  'Duplicado'),
        ('error',      'Error'),
    ], string='Estado')
    mensaje        = fields.Char(string='Detalle')
