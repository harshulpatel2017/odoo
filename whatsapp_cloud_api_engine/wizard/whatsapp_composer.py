# -*- coding: utf-8 -*-
import html
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WhatsAppComposer(models.TransientModel):
    _name = 'whatsapp.composer'
    _description = 'Interactive WhatsApp Message Composer'

    partner_id = fields.Many2one('res.partner', string='Recipient', required=True)
    phone = fields.Char(
        string='Recipient Phone Number', required=True,
        help='E.164 international phone number with country code (e.g. +919876543210)'
    )
    template_id = fields.Many2one('whatsapp.template', string='Use Template')
    use_meta_template = fields.Boolean(
        string='Send as Meta Template Payload',
        default=False,
        help='Enable only if this template code is already approved in Meta WhatsApp Manager (e.g. hello_world). Leave OFF to send formatted text & PDF directly inside a 24h WhatsApp session.'
    )
    body = fields.Text(string='Message Content', required=True)
    res_model = fields.Char(string='Related Model')
    res_id = fields.Integer(string='Related Record ID')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'wa_composer_attachment_rel', 'wizard_id', 'attachment_id',
        string='PDF / Media Attachments'
    )
    preview_html = fields.Html(string='Live WhatsApp Preview', compute='_compute_preview_html')

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id:
            if self.template_id.code == 'hello_world':
                self.use_meta_template = True
            if self.res_model and self.res_id and self.res_model in self.env:
                record = self.env[self.res_model].browse(self.res_id)
                if record.exists():
                    self.body = self.template_id.render_body(record)
                    att = self.template_id.generate_attachment(record)
                    if att:
                        self.attachment_ids = [(6, 0, [att.id])]
            else:
                self.body = self.template_id.render_body(False)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            raw_phone = self.partner_id.phone or getattr(self.partner_id, 'mobile', '')
            self.phone = self.partner_id.whatsapp_number or self.partner_id._sanitize_whatsapp_phone(raw_phone)

    @api.depends('body', 'phone', 'attachment_ids')
    def _compute_preview_html(self):
        for rec in self:
            safe_body = html.escape(rec.body or '').replace('\n', '<br/>')
            att_badges = ''
            if rec.attachment_ids:
                att_names = ', '.join(rec.attachment_ids.mapped('name'))
                att_badges = f"""
                <div style="background:#e2f7cb;padding:6px 10px;border-radius:6px;margin-bottom:8px;font-size:12px;display:flex;align-items:center;gap:6px;border:1px solid #c3e6a8;">
                    <span>📄</span>
                    <strong>PDF Attachment:</strong> {html.escape(att_names)}
                </div>
                """

            rec.preview_html = f"""
            <div style="background:#efeae2;padding:20px;border-radius:12px;max-width:520px;margin:auto;box-shadow:inset 0 0 10px rgba(0,0,0,0.05);">
                <div style="background:#d9fdd3;padding:12px 16px;border-radius:8px 8px 2px 8px;box-shadow:0 1px 2px rgba(0,0,0,0.15);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#111b21;">
                    {att_badges}
                    <div style="font-size:13.5px;line-height:1.5;">{safe_body or '<em style="color:#888;">Type your message above...</em>'}</div>
                    <div style="text-align:right;font-size:10.5px;color:#667781;margin-top:4px;">
                        Just now <span style="color:#53bdeb;font-weight:bold;">✓✓</span>
                    </div>
                </div>
                <div style="text-align:center;font-size:11px;color:#8696a0;margin-top:10px;">
                    Recipient: <strong>{html.escape(rec.phone or 'No phone specified')}</strong>
                </div>
            </div>
            """

    def action_send_whatsapp(self):
        """Create message log and trigger immediate dispatch."""
        self.ensure_one()
        if not self.phone:
            raise UserError(_('A valid WhatsApp phone number is required.'))
        if not self.body:
            raise UserError(_('Message content cannot be empty.'))

        msg_type = 'template' if (self.template_id and (self.use_meta_template or self.template_id.code == 'hello_world')) else ('document' if self.attachment_ids else 'text')

        log = self.env['whatsapp.message.log'].create({
            'partner_id': self.partner_id.id,
            'phone': self.phone,
            'message_type': msg_type,
            'template_id': self.template_id.id if self.template_id else False,
            'use_meta_template': self.use_meta_template,
            'body': self.body,
            'res_model': self.res_model,
            'res_id': self.res_id,
            'attachment_ids': [(6, 0, self.attachment_ids.ids)],
        })

        log.action_send()

        if log.state == 'failed':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WhatsApp Dispatch Failed (%s)') % log.name,
                    'message': log.error_message or _('Check WhatsApp Audit Logs for details.'),
                    'type': 'danger',
                    'sticky': True,
                }
            }

        is_sandbox = self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp_cloud_api_engine.sandbox_mode', 'False'
        ) == 'True'

        title = _('WhatsApp Message Sent (Sandbox)') if is_sandbox else _('WhatsApp Message Sent!')
        message = _('Message dispatched successfully to %s. Reference: %s') % (self.phone, log.name)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }
