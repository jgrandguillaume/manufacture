
# -*- coding: utf-8 -*-
# © 2016 Ucamco - Wim Audenaert <wim.audenaert@ucamco.com>
# © 2016 Eficent Business and IT Consulting Services S.L.
# - Jordi Ballester Alomar <jordi.ballester@eficent.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
#
{
    'name': 'Multi Level MRP',
    'version': '8.0.1.0.0',
    'author': 'Ucamco, '
              'Odoo Community Association (OCA)',
    'summary': 'Adds an MRP Scheduler',
    'website': 'http://www.ucamco.com',
    'category': 'Manufacturing',
    'depends': [
        'mrp',
        'stock',
        'purchase',
        'purchase_requisition',
        'warning',
    ],
    'data': [
        'views/mrp_forecast_view.xml',
        'views/product_view.xml',
        'views/mrp_product_view.xml',
        'wizards/multi_level_mrp_view.xml',
        'wizards/mrp_move_create_po_view.xml',
        'views/mrp_menuitem.xml',
        'data/multi_level_mrp_cron.xml',
    ],
    'installable': True,
    'application': True,
}
