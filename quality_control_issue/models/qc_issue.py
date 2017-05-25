# -*- coding: utf-8 -*-
# Copyright 2017 Eficent Business and IT Consulting Services S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import api, fields, models
import openerp.addons.decimal_precision as dp


class QualityControlIssue(models.Model):
    _name = "qc.issue"
    _description = "Quality Control Issue"
    _inherit = "mail.thread"

    @api.model
    def create(self, vals):
        vals['name'] = self.env['ir.sequence'].next_by_code(
            'qc.issue') or ''
        return super(QualityControlIssue, self).create(vals)

    @api.one
    def _get_uom(self):
        self.product_uom = self.product_id.product_tmpl_id.uom_id

    name = fields.Char(readonly=True)
    state = fields.Selection(
        selection=[("new", "New"),
                   ("progress", "In Progress"),
                   ("done", "Done"),
                   ("cancel", "Cancel")], default="new",
        track_visibility='onchange')
    product_id = fields.Many2one(
        comodel_name="product.product", string="Product",
        readonly=True, states={"new": [("readonly", False)]},
        required=True)
    product_tracking = fields.Selection(related="product_id.tracking")
    product_qty = fields.Float(
        string="Product Quantity", required=True, default=1.0,
        readonly=True, states={"new": [("readonly", False)]},
        digits_compute=dp.get_precision("Product Unit of Measure"))
    product_uom = fields.Many2one(
        comodel_name="product.uom", string="Product Unit of Measure",
        required=True, default=_get_uom,
        readonly=True, states={"new": [("readonly", False)]},)
    lot_id = fields.Many2one(
        comodel_name="stock.production.lot", string="Lot/Serial Number",
        readonly=True, states={"new": [("readonly", False)]},)
    location_id = fields.Many2one(
        comodel_name="stock.location", string="Location",
        readonly=True, states={"new": [("readonly", False)]},)
    inspector_id = fields.Many2one(
        comodel_name="res.users", string="Inspector",
        track_visibility="onchange",
        readonly=True, states={"new": [("readonly", False)]},
        default=lambda self: self.env.user, required=True)
    responsible_id = fields.Many2one(
        comodel_name="res.users", string="Assigned to",
        track_visibility="onchange",
        states={"done": [("readonly", True)]},)
    description = fields.Text(
        states={"done": [("readonly", True)]},)
    problem_track_ids = fields.Many2many(
        comodel_name="qc.problem.track", string="Problems",
        relation="qc_issue_problem_rel", column1="qc_issue_id",
        column2="qc_problem_id",
        states={"done": [("readonly", True)]},)

    @api.multi
    def action_confirm(self):
        self.write({'state': 'progress'})

    @api.multi
    def action_done(self):
        self.write({'state': 'done'})

    @api.multi
    def action_cancel(self):
        self.write({'state': 'cancel'})

    @api.onchange('product_id')
    def _onchange_product_id(self):
        self.product_uom = self.product_id.product_tmpl_id.uom_id
        if self.lot_id.product_id != self.product_id:
            self.lot_id = False
        if self.product_id:
            return {'domain': {
                'lot_id': [('product_id', '=', self.product_id.id)]}}
        return {'domain': {'lot_id': []}}

    @api.onchange("lot_id")
    def _onchange_lot_id(self):
        product = self.lot_id.product_id
        if product:
            self.product_id = product
            self.product_uom = product.product_tmpl_id.uom_id
