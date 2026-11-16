# -*- coding: utf-8 -*-
{
    'name': 'Compras FEL Guatemala',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Guatemala',
    'summary': 'Registro de compras FEL con importación XML del SAT Guatemala',
    'description': """
        Módulo de Compras FEL para Guatemala
        =====================================
        - Póliza de Compras: agrupa una o varias facturas FEL
        - Importación de XML del SAT (individual o ZIP)
        - Validación de archivos DTE guatemaltecos
        - Detección automática de tipo: FACT, FPEQ, RDON, anuladas, notas de crédito
        - Detección automática de IDP (combustible)
        - Generación de asientos contables individuales por factura
        - Libro de Compras con columnas SAT: Bienes, Servicios, Combustible,
          Pequeño Contribuyente, Exentas, IVA, Venta Neta, Total
    """,
    'author': 'Procesos Eficientes GT',
    'license': 'LGPL-3',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/gt_compras_data.xml',
        'views/gt_poliza_compra_views.xml',
        'views/gt_compras_menu.xml',
        'wizard/gt_wizard_carga_xml_views.xml',
        'report/gt_libro_compras_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'gt_compras_fel/static/src/css/gt_compras.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
