# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_open_whatsapp_composer(self):
        """Open WhatsApp interactive composer pre-configured for this Sales Order."""
        self.ensure_one()
        template = self.env['whatsapp.template'].search([
            ('model_name', '=', 'sale.order'),
            ('active', '=', True)
        ], limit=1)

        raw_phone = self.partner_id.phone or getattr(self.partner_id, 'mobile', '')
        phone = self.partner_id.whatsapp_number or self.partner_id._sanitize_whatsapp_phone(raw_phone)

        rendered_body = template.render_body(self) if template else ''
        attachment = template.generate_attachment(self) if template else False

        return {
            'name': _('Send WhatsApp Message'),
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.composer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_phone': phone,
                'default_template_id': template.id if template else False,
                'default_body': rendered_body,
                'default_res_model': self._name,
                'default_res_id': self.id,
                'default_attachment_ids': [(4, attachment.id)] if attachment else [],
            }
        }

    def action_confirm(self):
        """Override order confirmation to trigger automated WhatsApp alert if enabled."""
        res = super(SaleOrder, self).action_confirm()
        auto_send = self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp_cloud_api_engine.auto_send_sale', 'False'
        ) == 'True'

        if auto_send:
            for order in self:
                template = self.env.ref('whatsapp_cloud_api_engine.wa_template_sale_order_confirmation', raise_if_not_found=False)
                if template and order.partner_id:
                    order._send_whatsapp_with_template(template)
        return res

    def _send_whatsapp_with_template(self, template):
        """Helper to create and dispatch WhatsApp message from template."""
        self.ensure_one()
        raw_phone = self.partner_id.phone or getattr(self.partner_id, 'mobile', '')
        phone = self.partner_id.whatsapp_number or self.partner_id._sanitize_whatsapp_phone(raw_phone)
        if not phone:
            return

        body = template.render_body(self)
        attachment = template.generate_attachment(self)

        log = self.env['whatsapp.message.log'].create({
            'partner_id': self.partner_id.id,
            'phone': phone,
            'message_type': 'template' if template.code else 'text',
            'template_id': template.id,
            'body': body,
            'res_model': self._name,
            'res_id': self.id,
            'attachment_ids': [(4, attachment.id)] if attachment else [],
        })
        log.action_send()
