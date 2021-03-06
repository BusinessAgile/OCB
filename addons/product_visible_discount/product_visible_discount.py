# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2008 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import SUPERUSER_ID
from openerp.osv import fields, osv
from openerp.tools.translate import _

class product_pricelist(osv.osv):
    _inherit = 'product.pricelist'

    _columns ={
        'visible_discount': fields.boolean('Visible Discount'),
    }
    _defaults = {
         'visible_discount': True,
    }


class sale_order_line(osv.osv):
    _inherit = "sale.order.line"

    def product_id_change(self, cr, uid, ids, pricelist, product, qty=0,
            uom=False, qty_uos=0, uos=False, name='', partner_id=False,
            lang=False, update_tax=True, date_order=False, packaging=False,
            fiscal_position=False, flag=False, context=None):

        def get_real_price_curency(res_dict, product_id, qty, uom, pricelist):
            """Retrieve the price before applying the pricelist"""
            item_obj = self.pool.get('product.pricelist.item')
            price_type_obj = self.pool.get('product.price.type')
            product_obj = self.pool.get('product.product')
            field_name = 'list_price'
            rule_id = res_dict.get(pricelist) and res_dict[pricelist][1] or False
            currency_id = None
            if rule_id:
                item_base = item_obj.read(cr, uid, [rule_id], ['base'])[0]['base']
                if item_base > 0:
                    price_type = price_type_obj.browse(cr, uid, item_base)
                    field_name = price_type.field
                    currency_id = price_type.currency_id

            product = product_obj.browse(cr, uid, product_id, context)
            product_read = product_obj.read(cr, uid, [product_id], [field_name], context=context)[0]

            if not currency_id:
                currency_id = product.company_id.currency_id.id
            factor = 1.0
            if uom and uom != product.uom_id.id:
                # the unit price is in a different uom
                factor = self.pool['product.uom']._compute_qty(cr, uid, uom, 1.0, product.uom_id.id)
            return product_read[field_name] * factor, currency_id

        def get_real_price(res_dict, product_id, qty, uom, pricelist):
            return get_real_price_curency(res_dict, product_id, qty, uom, pricelist)[0]


        res=super(sale_order_line, self).product_id_change(cr, uid, ids, pricelist, product, qty,
            uom, qty_uos, uos, name, partner_id,
            lang, update_tax, date_order, packaging=packaging, fiscal_position=fiscal_position, flag=flag, context=context)

        context = {'lang': lang, 'partner_id': partner_id}
        result=res['value']
        pricelist_obj=self.pool.get('product.pricelist')
        product_obj = self.pool.get('product.product')
        account_tax_obj = self.pool.get('account.tax')
        if product and pricelist and self.pool.get('res.users').has_group(cr, uid, 'sale.group_discount_per_so_line'):
            if result.get('price_unit',False):
                price=result['price_unit']
            else:
                return res
            uom = result.get('product_uom', uom)
            product = product_obj.browse(cr, uid, product, context)
            pricelist_context = dict(context, uom=uom, date=date_order)
            list_price = pricelist_obj.price_rule_get(cr, uid, [pricelist],
                    product.id, qty or 1.0, partner_id, context=pricelist_context)

            so_pricelist = pricelist_obj.browse(cr, uid, pricelist, context=context)

            new_list_price, currency_id = get_real_price_curency(list_price, product.id, qty, uom, pricelist)

            # The superuser is used by website_sale in order to create a sale order. We need to make
            # sure we only select the taxes related to the company of the partner. This should only
            # apply if the partner is linked to a company.
            if uid == SUPERUSER_ID and context.get('company_id'):
                taxes = product.taxes_id.filtered(lambda r: r.company_id.id == context['company_id'])
            else:
                taxes = product.taxes_id
            new_list_price = account_tax_obj._fix_tax_included_price(cr, uid, new_list_price, taxes, result.get('tax_id', []))

            if so_pricelist.visible_discount and list_price[pricelist][0] != 0 and new_list_price != 0:
                if product.company_id and so_pricelist.currency_id.id != product.company_id.currency_id.id:
                    # new_list_price is in company's currency while price in pricelist currency
                    ctx = context.copy()
                    ctx['date'] = date_order
                    new_list_price = self.pool['res.currency'].compute(cr, uid,
                        currency_id.id, so_pricelist.currency_id.id,
                        new_list_price, context=ctx)
                discount = (new_list_price - price) / new_list_price * 100
                if discount > 0:
                    result['price_unit'] = new_list_price
                    result['discount'] = discount
                else:
                    result['discount'] = 0.0
            else:
                result['discount'] = 0.0
        else:
            result['discount'] = 0.0
        return res
