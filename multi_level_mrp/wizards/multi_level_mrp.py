# -*- coding: utf-8 -*-
# © 2016 Ucamco - Wim Audenaert <wim.audenaert@ucamco.com>
# © 2016 Eficent Business and IT Consulting Services S.L.
# - Jordi Ballester Alomar <jordi.ballester@eficent.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from openerp import models, fields, api
from datetime import date, datetime, timedelta


class MultiLevelMrp(models.TransientModel):
    _name = 'multi.level.mrp'

    @api.model
    def _prepare_mrp_product_data(self, product):
        main_supplier_id = False
        sequence = 9999
        for supplier in product.product_tmpl_id.seller_ids:
            if supplier.sequence < sequence:
                sequence = supplier.sequence
                main_supplier_id = supplier.name.id
        supply_method = 'produce'
        for route in product.product_tmpl_id.route_ids:
            if route.name == 'Buy':
                supply_method = 'buy'
        return {
            'product_id': product.id,
            'mrp_qty_available': product.qty_available,
            'mrp_llc': product.llc,
            'nbr_mrp_actions': 0,
            'nbr_mrp_actions_4w': 0,
            'name': product.name_template,
            'supply_method': supply_method,
            'main_supplier_id': main_supplier_id,
            }

    @api.model
    def _prepare_mrp_move_data(self, fc, fc_id, mrpproduct):
        mrp_type = 'd'
        origin = 'fc'
        mrp_date = date.today()
        if datetime.date(datetime.strptime(fc_id.date,
                                           '%Y-%m-%d')) > date.today():
            mrp_date = datetime.date(datetime.strptime(
                fc_id.date, '%Y-%m-%d'))
        return {
            'product_id': fc.product_id.id,
            'mrp_product_id': mrpproduct.id,
            'production_id': None,
            'purchase_order_id': None,
            'purchase_line_id': None,
            'sale_order_id': None,
            'sale_line_id': None,
            'stock_move_id': None,
            'mrp_qty': -fc_id.qty_forecast,
            'current_qty': -fc_id.qty_forecast,
            'mrp_date': mrp_date,
            'current_date': mrp_date,
            'mrp_action': 'none',
            'mrp_type': mrp_type,
            'mrp_processed': False,
            'mrp_origin': origin,
            'mrp_order_number': None,
            'parent_product_id': None,
            'running_availability': 0.00,
            'name': 'Forecast',
            'state': 'confirmed',
        }

    @api.one
    def run_multi_level_mrp(self):
        self = self.with_context(auditlog_disabled=True)
        
        print 'LOAD MRP PRODUCTS'
        products = self.env['product.product'].search_read(
            [('active', '=', True), ('mrp_exclude', '!=', True)], ['id'])
        product_ids = []
        for product in products:
            product_ids.append(product['id'])
        print 'END LOAD MRP PRODUCTS'
        
        # Some part of the code with the new API is replaced by
        # sql statements due to performance issues when the auditlog is
        # installed
        print 'START MRP CLEANUP'
        self.env['mrp.move'].search([('id', '!=', 0)]).unlink()
        self.env['mrp.product'].search([('id', '!=', 0)]).unlink()
        sql_stat = 'update product_product set mrp_product_id = NULL'
        self.env.cr.execute(sql_stat)
        print 'END MRP CLEANUP'
        
        print 'START LOW LEVEL CODE CALCULATION'
        counter = 999999
        sql_stat = 'update product_product set llc = 0'
        self.env.cr.execute(sql_stat)
        sql_stat = 'SELECT count(id) AS counter FROM product_product WHERE ' \
                   'llc = %d' % (0, )
        self.env.cr.execute(sql_stat)
        sql_res = self.env.cr.dictfetchone()
        if sql_res:
            counter = sql_res['counter']
        print 'LOW LEVEL CODE 0 FINISHED - NBR PRODUCTS: ', counter
        
        llc = 0
        while counter != 999999:
            self.env.cr.commit()
            llc += 1
            sql_stat = '''UPDATE product_product p1 SET llc = %d
                          FROM mrp_bom_line b1, mrp_bom b2, product_product p2
                          WHERE p1.llc = (%d - 1)
                            AND p1.id = b1.product_id
                            AND b1.bom_id = b2.id
                            AND p2.product_tmpl_id = b2.product_tmpl_id
                            AND p2.llc = (%d - 1)''' % (llc, llc, llc, )
            self.env.cr.execute(sql_stat)
            sql_stat = 'SELECT count(id) AS counter FROM product_product ' \
                       'WHERE llc = %d' % (llc, )
            self.env.cr.execute(sql_stat)
            sql_res = self.env.cr.dictfetchone()
            if sql_res:
                counter = sql_res['counter']
            print 'LOW LEVEL CODE ', llc, ' FINISHED - NBR PRODUCTS: ', counter
            if counter == 0:
                counter = 999999
        mrp_lowest_llc = llc
        self.env.cr.commit()
        print 'END LOW LEVEL CODE CALCULATION'
        
        print 'CALCULATE MRP APPLICABLE'
        sql_stat = '''UPDATE product_product SET mrp_applicable = False;'''
        self.env.cr.execute(sql_stat)
        
        sql_stat = '''
UPDATE product_product SET mrp_applicable=True
FROM product_template
WHERE product_tmpl_id = product_template.id
  AND product_template.active = True
  AND product_template.type = 'product'
  AND mrp_minimum_stock > (SELECT sum(qty) FROM stock_quant, stock_location
                           WHERE stock_quant.product_id = product_product.id
                             AND stock_quant.location_id = stock_location.id
                             AND stock_location.usage = 'internal');'''
        self.env.cr.execute(sql_stat)

        sql_stat = '''
UPDATE product_product SET mrp_applicable=True
FROM product_template
WHERE product_tmpl_id = product_template.id
  AND product_template.active = True
  AND product_template.type = 'product'
  AND product_product.id in (SELECT distinct product_id FROM stock_move WHERE
  state <> 'draft' AND state <> 'cancel');'''
        self.env.cr.execute(sql_stat)

        sql_stat = '''
UPDATE product_product SET mrp_applicable=True
FROM product_template
WHERE product_tmpl_id = product_template.id
  AND product_template.active = True
  AND product_template.type = 'product'
  AND llc > 0;'''
        self.env.cr.execute(sql_stat)

        sql_stat = '''
UPDATE product_product SET mrp_applicable=True
FROM mrp_forecast_product
WHERE product_product.id = mrp_forecast_product.product_id;'''
        self.env.cr.execute(sql_stat)

        self.env.cr.commit()
        counter = 0
        sql_stat = 'SELECT count(id) AS counter FROM product_product WHERE ' \
                   'mrp_applicable = True'
        self.env.cr.execute(sql_stat)
        sql_res = self.env.cr.dictfetchone()
        if sql_res:
            counter = sql_res['counter']
        print 'END CALCULATE MRP APPLICABLE: ', counter
        
        print 'START MRP INITIALISATION'
        products = self.env['product.product'].search(
            [('mrp_applicable', '=', True)])
        init_counter = 0
        for product in products:
            if product.mrp_exclude:
                continue
            init_counter += 1
            print 'MRP INIT:', init_counter, ' - ', product.default_code
            mrp_product_data = self._prepare_mrp_product_data(product)
            mrp_product = self.env['mrp.product'].create(mrp_product_data)
            product.mrp_product_id = mrp_product
            
            forecast = self.env['mrp.forecast.product'].search(
                [('product_id', '=', product.id)])
            for fc in forecast: 
                for fc_id in fc.mrp_forecast_ids:
                    mrp_move_data = self._prepare_mrp_move_data(self, fc,
                                                                fc_id,
                                                                mrp_product)
                    self.env['mrp.move'].create(mrp_move_data)
            
            moves = self.env['stock.move'].search(
                [('product_id', '=', product.id),
                 ('state', '!=', 'done'),
                 ('state', '!=', 'cancel'),
                 ('product_qty', '>', 0.00)])

            for move in moves:
                if (move.location_id.usage == 'internal' and
                        move.location_dest_id.usage != 'internal') \
                        or (move.location_id.usage != 'internal' and
                                    move.location_dest_id.usage == 'internal'):
                    if move.location_id.usage == 'internal':
                        mrp_type = 'd'
                        productqty = -move.product_qty
                    else:
                        mrp_type = 's'
                        productqty = move.product_qty
                    po = None
                    po_line = None
                    so = None
                    so_line = None
                    mo = None
                    origin = None
                    order_number = None
                    parent_product_id = None
                    if move.purchase_line_id:
                        order_number = move.purchase_line_id.order_id.name
                        origin = 'po'
                        po = move.purchase_line_id.order_id.id
                        po_line = move.purchase_line_id.id
                    if move.production_id:
                        order_number = move.production_id.name
                        origin = 'mo'
                        mo = move.production_id.id
                    else:
                        if move.move_dest_id:
                            if move.move_dest_id.production_id:
                                order_number = \
                                    move.move_dest_id.production_id.name
                                origin = 'mo'
                                mo = move.move_dest_id.production_id.id
                                if move.move_dest_id.production_id.product_id:
                                    parent_product_id = \
                                        move.move_dest_id.production_id.product_id.id
                                else:
                                    parent_product_id = \
                                        move.move_dest_id.product_id.id
                    if order_number is None:
                        order_number = move.name
                    mrp_date = date.today()
                    if datetime.date(datetime.strptime(move.date, '%Y-%m-%d %H:%M:%S')) > date.today():
                        mrp_date = datetime.date(datetime.strptime(move.date, '%Y-%m-%d %H:%M:%S'))
                    self.env['mrp.move'].create({
                        'product_id': move.product_id.id,
                        'mrp_product_id': mrp_product.id,
                        'production_id': mo,
                        'purchase_order_id': po,
                        'purchase_line_id': po_line,
                        'sale_order_id': so,
                        'sale_line_id': so_line,
                        'stock_move_id': move.id,
                        'mrp_qty': productqty,
                        'current_qty': productqty,
                        'mrp_date': mrp_date,
                        'current_date': move.date,
                        'mrp_action': 'none',
                        'mrp_type': mrp_type,
                        'mrp_processed': False,
                        'mrp_origin': origin,
                        'mrp_order_number': order_number,
                        'parent_product_id': parent_product_id,
                        'running_availability': 0.00,
                        'name': order_number,
                        'state': move.state,
                    })
            
            for poreq in product.purchase_requisition_ids:
                if poreq.requisition_id.state == 'draft' and \
                                poreq.product_qty > 0.00:
                    mrp_date = date.today()
                    if poreq.requisition_id.schedule_date and \
                                    datetime.date(datetime.strptime(
                                        poreq.requisition_id.schedule_date,
                                        '%Y-%m-%d %H:%M:%S')) > date.today():
                        mrp_date = datetime.date(datetime.strptime(
                            poreq.requisition_id.schedule_date,
                            '%Y-%m-%d %H:%M:%S'))
                    self.env['mrp.move'].create({
                        'product_id': poreq.product_id.id,
                        'mrp_product_id': mrp_product.id,
                        'production_id': None,
                        'purchase_order_id': None,
                        'purchase_line_id': None,
                        'sale_order_id': None,
                        'sale_line_id': None,
                        'stock_move_id': None,
                        'mrp_qty': poreq.product_qty,
                        'current_qty': poreq.product_qty,
                        'mrp_date': mrp_date,
                        'current_date': poreq.requisition_id.schedule_date,
                        'mrp_action': 'none',
                        'mrp_type': 's',
                        'mrp_processed': False,
                        'mrp_origin': 'pr',
                        'mrp_order_number': poreq.requisition_id.name,
                        'parent_product_id': None,
                        'running_availability': 0.00,
                        'name': poreq.requisition_id.name,    
                        'state': poreq.requisition_id.state,
                    })

            for poline in product.purchase_order_line_ids:
                if (poline.order_id.state == 'draft' or
                            poline.order_id.state == 'confirmed') and \
                                poline.product_qty > 0.00:
                    mrp_date = date.today()
                    if datetime.date(datetime.strptime(
                            poline.date_planned, '%Y-%m-%d')) > date.today():
                        mrp_date = datetime.date(datetime.strptime(
                            poline.date_planned, '%Y-%m-%d'))
                    self.env['mrp.move'].create({
                        'product_id': poline.product_id.id,
                        'mrp_product_id': mrp_product.id,
                        'production_id': None,
                        'purchase_order_id': poline.order_id.id,
                        'purchase_line_id': poline.id,
                        'sale_order_id': None,
                        'sale_line_id': None,
                        'stock_move_id': None,
                        'mrp_qty': poline.product_qty,
                        'current_qty': poline.product_qty,
                        'mrp_date': mrp_date,
                        'current_date': poline.date_planned,
                        'mrp_action': 'none',
                        'mrp_type': 's',
                        'mrp_processed': False,
                        'mrp_origin': 'po',
                        'mrp_order_number': poline.order_id.name,
                        'parent_product_id': None,
                        'running_availability': 0.00,
                        'name': poline.order_id.name,    
                        'state': poline.order_id.state,
                    })

            for mo in product.manufacturing_order_ids:
                if mo.state == 'draft' and mo.product_qty > 0.00:
                    mrp_date = date.today()
                    if datetime.date(datetime.strptime(
                            mo.date_planned, '%Y-%m-%d %H:%M:%S')) > date.today():
                        mrp_date = datetime.date(datetime.strptime(
                            mo.date_planned, '%Y-%m-%d %H:%M:%S'))
                    self.env['mrp.move'].create({
                        'product_id': mo.product_id.id,
                        'mrp_product_id': mrp_product.id,
                        'production_id': mo.id,
                        'purchase_order_id': None,
                        'purchase_line_id': None,
                        'sale_order_id': None,
                        'sale_line_id': None,
                        'stock_move_id': None,
                        'mrp_qty': mo.product_qty,
                        'current_qty': mo.product_qty,
                        'mrp_date': mrp_date,
                        'current_date': mo.date_planned,
                        'mrp_action': 'none',
                        'mrp_type': 's',
                        'mrp_processed': False,
                        'mrp_origin': 'mo',
                        'mrp_order_number': mo.name,
                        'parent_product_id': None,
                        'running_availability': 0.00,
                        'name': mo.name,    
                        'state': mo.state,
                    })
                    mrp_date_demand = mrp_date-timedelta(days=product.mrp_lead_time)
                    if mrp_date_demand < date.today():
                        mrp_date_demand = date.today()
                    if mo.bom_id and mo.bom_id.bom_line_ids:
                        for bomline in mo.bom_id.bom_line_ids:
                            if bomline.product_qty > 0.00:
                                if bomline.date_start ==  None or \
                                        (bomline.date_start and
                                                 datetime.date(
                                                     datetime.strptime(
                                                         bomline.date_start,
                                                         '%Y-%m-%d')) <
                                                 mrp_date_demand):
                                    if bomline.date_stop == None or \
                                            (bomline.date_stop and
                                                     datetime.date(
                                                         datetime.strptime(
                                                             bomline.date_stop,
                                                             '%Y-%m-%d')) >
                                                     mrp_date_demand):
                                        self.env['mrp.move'].create({
                                            'product_id': bomline.product_id.id,
                                            'mrp_product_id':
                                                bomline.product_id.mrp_product_id.id,
                                            'production_id': mo.id,
                                            'purchase_order_id': None,
                                            'purchase_line_id': None,
                                            'sale_order_id': None,
                                            'sale_line_id': None,
                                            'stock_move_id': None,
                                            'mrp_qty':
                                                -(mo.product_qty *
                                                  bomline.product_qty),
                                            'current_qty': None,
                                            'mrp_date': mrp_date_demand,
                                            'current_date': None,
                                            'mrp_action': 'none',
                                            'mrp_type': 'd',
                                            'mrp_processed': False,
                                            'mrp_origin': 'mo',
                                            'mrp_order_number': mo.name,
                                            'parent_product_id': mo.product_id.id,
                                            'name': ('Demand Bom Explosion: '
                                                     + mo.name).replace(
                                                'Demand Bom Explosion: '
                                                'Demand Bom Explosion: ',
                                                'Demand Bom Explosion: '),
                                        })
            self.env.cr.commit()
        print 'END MRP INITIALISATION'
        
        print 'START MRP CALCULATION'
        llc = 0
         
        while mrp_lowest_llc > llc:
            self.env.cr.commit()
            products = self.env['mrp.product'].search([('mrp_llc', '=', llc)])
            llc += 1
            counter = 0
            for product in products:
                nbr_create = 0
                onhand = product.mrp_qty_available
                if product.mrp_nbr_days == 0:
                    for move in product.mrp_move_ids:
                        if move.mrp_action == 'none':
                            if (onhand + move.mrp_qty) < \
                                    product.mrp_minimum_stock:
                                name = move.name
                                qtytoorder = product.mrp_minimum_stock - \
                                             onhand - move.mrp_qty
                                cm = self.create_move(
                                    mrp_product_id=product.id,
                                    mrp_date=move.mrp_date,
                                    mrp_qty=qtytoorder, name=name)
                                qty_ordered = cm['qty_ordered']
                                onhand = onhand + move.mrp_qty + qty_ordered
                                nbr_create += 1
                            else:
                                onhand = onhand + move.mrp_qty
                else:
                    last_date = None
                    last_qty = 0.00
                    move_ids = []
                    for move in product.mrp_move_ids:
                        move_ids.append(move.id)
                    for move_id in move_ids:
                        move_rec = self.env['mrp.move'].search([('id', '=',
                                                                 move_id)])
                        for move in move_rec:
                            if move.mrp_action == 'none':
                                if last_date is not None:
                                    if datetime.date(
                                            datetime.strptime(
                                                move.mrp_date, '%Y-%m-%d')) > \
                                                    last_date+timedelta(
                                                days=product.mrp_nbr_days):
                                        if (onhand + last_qty + move.mrp_qty) \
                                                < product.mrp_minimum_stock \
                                                or (onhand + last_qty) \
                                                < product.mrp_minimum_stock:
                                            name = 'Grouped Demand for ' \
                                                   '%d Days' % (
                                                product.mrp_nbr_days, )
                                            qtytoorder = \
                                                product.mrp_minimum_stock - \
                                                onhand - last_qty
                                            cm = self.create_move(
                                                mrp_product_id=product.id,
                                                mrp_date=last_date,
                                                mrp_qty=qtytoorder,
                                                name=name)
                                            qty_ordered = cm['qty_ordered']
                                            onhand = onhand + last_qty + qty_ordered
                                            last_date = None
                                            last_qty = 0.00
                                            nbr_create += 1
                                if (onhand + last_qty + move.mrp_qty) < \
                                        product.mrp_minimum_stock or \
                                                (onhand + last_qty) < \
                                                product.mrp_minimum_stock:
                                    if last_date is None:
                                        last_date = datetime.date(
                                            datetime.strptime(move.mrp_date,
                                                              '%Y-%m-%d'))
                                        last_qty = move.mrp_qty
                                    else:
                                        last_qty = last_qty + move.mrp_qty
                                else:
                                    last_date = datetime.date(
                                        datetime.strptime(move.mrp_date,
                                                          '%Y-%m-%d'))
                                    onhand = onhand + move.mrp_qty
                    if last_date is not None and last_qty != 0.00:
                        name = 'Grouped Demand for %d Days' % \
                               (product.mrp_nbr_days, )
                        qtytoorder = product.mrp_minimum_stock - onhand - last_qty
                        cm = self.create_move(
                            mrp_product_id=product.id, mrp_date=last_date,
                            mrp_qty=qtytoorder, name=name)
                        qty_ordered = cm['qty_ordered']
                        onhand = onhand + qty_ordered
                        nbr_create = nbr_create + 1
                if onhand < product.mrp_minimum_stock and nbr_create == 0:
                    name = 'Minimum Stock'
                    qtytoorder = product.mrp_minimum_stock - onhand
                    cm = self.create_move(mrp_product_id=product.id,
                                          mrp_date=date.today(),
                                          mrp_qty=qtytoorder, name=name)
                    qty_ordered = cm['qty_ordered']
                    onhand += qty_ordered
                counter += 1
                self.env.cr.commit()

            print 'MRP CALCULATION LLC ', llc - 1, \
                ' FINISHED - NBR PRODUCTS: ', counter
            if llc < 0:
                counter = 999999
                 
        self.env.cr.commit()
        print 'END MRP CALCULATION'

        print 'START MRP FINAL PROCESS'
        product_ids = self.env['mrp.product'].search([('mrp_llc', '<', 9999)])
        for product in product_ids:
            qoh = product.mrp_qty_available
            nbr_actions = 0
            nbr_actions_4w = 0
            sql_stat = 'SELECT id, mrp_date, mrp_qty, mrp_action FROM ' \
                       'mrp_move WHERE mrp_product_id = %d ORDER BY ' \
                       'mrp_date, ' \
                       'mrp_type desc, id' % (product.id, )
            self.env.cr.execute(sql_stat)
            for sql_res in self.env.cr.dictfetchall():
                qoh = qoh + sql_res['mrp_qty']
                self.env['mrp.move'].search(
                    [('id', '=', sql_res['id'])]).write(
                    {'running_availability': qoh})
            
            for move in product.mrp_move_ids:
                if move.mrp_action != 'none':
                    nbr_actions += 1
                if move.mrp_date:
                    if move.mrp_action != 'none' and \
                                    datetime.date(datetime.strptime(
                                        move.mrp_action_date, '%Y-%m-%d')) < \
                                            date.today()+timedelta(days=29):
                        nbr_actions_4w += 1
            if nbr_actions > 0:
                self.env['mrp.product'].search(
                    [('id', '=', product.id)]).write(
                    {'nbr_mrp_actions': nbr_actions,
                     'nbr_mrp_actions_4w': nbr_actions_4w})
            self.env.cr.commit()
        print 'END MRP FINAL PROCESS'

    @api.model
    def create_move(self, mrp_product_id, mrp_date, mrp_qty, name):
        self = self.with_context(auditlog_disabled=True)
        
        values = {}
        if not isinstance(mrp_date, date):
            mrp_date = datetime.date(datetime.strptime(mrp_date, '%Y-%m-%d'))
            
        qty_ordered = 0.00
        products = self.env['mrp.product'].search([('id','=',mrp_product_id)])
        for product in products:
            if product.supply_method == 'buy':
                if product.purchase_requisition:
                    mrp_action = 'pr'
                else:
                    mrp_action = 'po'
            else:
                mrp_action = 'mo'

            if mrp_date < date.today():
                mrp_date_supply = date.today()
            else:
                mrp_date_supply = mrp_date
            
            mrp_action_date = mrp_date-timedelta(days=product.mrp_lead_time)
                            
            qty_ordered = 0.00
            qty_to_order = mrp_qty
            while qty_ordered < mrp_qty:
                qty = 0.00
                if product.mrp_maximum_order_qty == 0.00 and \
                                product.mrp_minimum_order_qty == 0.00:
                    qty = qty_to_order
                else:
                    if qty_to_order < product.mrp_minimum_order_qty:
                        qty = product.mrp_minimum_order_qty
                    else:
                        if product.mrp_maximum_order_qty and qty_to_order > \
                                product.mrp_maximum_order_qty:
                            qty = product.mrp_maximum_order_qty
                        else:
                            qty = qty_to_order
                qty_to_order = qty_to_order - qty
                        
                mrpmove_id = self.env['mrp.move'].create({
                    'product_id': product.product_id.id,
                    'mrp_product_id': product.id,
                    'production_id': None,
                    'purchase_order_id': None,
                    'purchase_line_id': None,
                    'sale_order_id': None,
                    'sale_line_id': None,
                    'stock_move_id': None,
                    'mrp_qty': qty,
                    'current_qty': None,
                    'mrp_date': mrp_date_supply,
                    'mrp_action_date': mrp_action_date,
                    'current_date': None,
                    'mrp_action': mrp_action,
                    'mrp_type': 's',
                    'mrp_processed': False,
                    'mrp_origin': None,
                    'mrp_order_number': None,
                    'parent_product_id': None,
                    'name': 'Supply: ' + name,
                })
                qty_ordered = qty_ordered + qty
            
                if mrp_action == 'mo':
                    mrp_date_demand = mrp_date-timedelta(days=product.mrp_lead_time)
                    if mrp_date_demand < date.today():
                        mrp_date_demand = date.today()
                    if not product.product_id.bom_ids:
                        continue
                    bomcount = 0
                    for bom in product.product_id.bom_ids:
                        if not bom.active or not bom.bom_line_ids:
                            continue
                        bomcount += 1
                        if bomcount != 1:
                            continue
                        for bomline in bom.bom_line_ids:
                            if bomline.product_qty <= 0.00:
                                continue
                            if bomline.date_start and datetime.date(
                                    datetime.strptime(
                                        bomline.date_start, '%Y-%m-%d')) > \
                                    mrp_date_demand:
                                continue
                            if bomline.date_stop and datetime.date(
                                    datetime.strptime(
                                        bomline.date_stop, '%Y-%m-%d')) < \
                                    mrp_date_demand:
                                continue

                            mrp_date_demand_2 = mrp_date_demand-timedelta(
                                days=(product.mrp_transit_delay+product.
                                      mrp_inspection_delay))
                            mrpmove_id2 = self.env['mrp.move'].create({
                                'product_id': bomline.product_id.id,
                                'mrp_product_id':
                                    bomline.product_id.mrp_product_id.id,
                                'production_id': None,
                                'purchase_order_id': None,
                                'purchase_line_id': None,
                                'sale_order_id': None,
                                'sale_line_id': None,
                                'stock_move_id': None,
                                'mrp_qty': -(qty * bomline.product_qty),
                                'current_qty': None,
                                'mrp_date': mrp_date_demand_2,
                                'current_date': None,
                                'mrp_action': 'none',
                                'mrp_type': 'd',
                                'mrp_processed': False,
                                'mrp_origin': 'mrp',
                                'mrp_order_number': None,
                                'parent_product_id': bom.product_id.id,
                                'name':
                                    ('Demand Bom Explosion: ' + name).replace(
                                        'Demand Bom Explosion: Demand Bom '
                                        'Explosion: ',
                                        'Demand Bom Explosion: '),
                            })
                            sql_stat = "INSERT INTO mrp_move_rel (" \
                                       "move_up_id, " \
                                       "move_down_id) values (%d, %d)" % \
                                       (mrpmove_id, mrpmove_id2, )
                            self.env.cr.execute(sql_stat)
        values['qty_ordered'] = qty_ordered
        print qty_ordered
        return values
