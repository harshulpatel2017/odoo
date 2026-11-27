# -*- coding: utf-8 -*-
import base64
import json
import time
import requests
import logging
from markupsafe import Markup, escape
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WhatsAppMessageLog(models.Model):
    _name = 'whatsapp.message.log'
    _description = 'WhatsApp Message Log & Audit Trail'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New')
    )
    partner_id = fields.Many2one('res.partner', string='Contact / Recipient', tracking=True)
    phone = fields.Char(
        string='Recipient Phone', required=True, tracking=True,
        help='E.164 formatted international phone number (e.g. +919876543210)'
    )
    direction = fields.Selection([
        ('outbound', 'Outbound (Sent)'),
        ('inbound', 'Inbound (Received)')
    ], string='Direction', default='outbound', required=True, tracking=True)
    message_type = fields.Selection([
        ('text', 'Free Text'),
        ('template', 'Meta Template'),
        ('document', 'Document / Media')
    ], string='Message Type', default='text', required=True)
    template_id = fields.Many2one('whatsapp.template', string='Template Used')
    use_meta_template = fields.Boolean(
        string='Dispatch as Meta Template Payload',
        default=False,
        help='If checked, dispatches Meta approved template JSON instead of free text / media.'
    )
    body = fields.Text(string='Message Content', tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'wa_log_attachment_rel', 'log_id', 'attachment_id',
        string='Attached Documents'
    )

    res_model = fields.Char(string='Origin Model', index=True)
    res_id = fields.Integer(string='Origin Record ID', index=True)
    res_name = fields.Char(string='Origin Document', compute='_compute_res_name', store=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed')
    ], string='Status', default='draft', tracking=True, index=True)

    is_sandbox = fields.Boolean(
        string='Sandbox Simulated', default=False, readonly=True,
        help='True if this message was generated and verified using the local sandbox simulator.'
    )
    waba_message_id = fields.Char(string='Meta Message ID (wamid)', copy=False, readonly=True, index=True)
    payload = fields.Text(string='JSON Request Payload', copy=False, readonly=True)
    response = fields.Text(string='JSON Response', copy=False, readonly=True)
    error_message = fields.Text(string='Failure Reason', copy=False, readonly=True, tracking=True)
    retry_count = fields.Integer(string='Retry Count', default=0, readonly=True)
    sent_date = fields.Datetime(string='Timestamp', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('whatsapp.message.log') or _('New')
        return super().create(vals_list)

    @api.depends('res_model', 'res_id')
    def _compute_res_name(self):
        for rec in self:
            if rec.res_model and rec.res_id and rec.res_model in self.env:
                target = self.env[rec.res_model].sudo().browse(rec.res_id)
                rec.res_name = target.display_name if target.exists() else f"{rec.res_model},{rec.res_id}"
            else:
                rec.res_name = False

    def action_send(self):
        """Execute message transmission via Meta Cloud API or Simulation Sandbox."""
        for rec in self:
            if not rec.phone:
                raise UserError(_('Recipient phone number is required.'))

            is_sandbox = self.env['ir.config_parameter'].sudo().get_param(
                'whatsapp_cloud_api_engine.sandbox_mode', 'False'
            ) == 'True'

            clean_digits = ''.join(filter(str.isdigit, rec.phone))

            if is_sandbox:
                rec._process_sandbox_send(clean_digits)
            else:
                rec._process_live_meta_send(clean_digits)

        return True

    def _process_sandbox_send(self, clean_digits):
        """Simulate message dispatch with realistic Meta Graph API JSON payload and responses."""
        self.ensure_one()
        mock_wamid = f"wamid.HBgMSkFURVNUX1NBTkRCT1gV{int(time.time())}_{self.id}"

        mock_payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_digits,
            "type": "template" if (self.template_id and self.use_meta_template) else ("document" if self.attachment_ids else "text"),
        }

        if self.template_id and self.use_meta_template:
            mock_payload["template"] = {
                "name": self.template_id.code,
                "language": {"code": self.template_id.language},
            }
        elif self.attachment_ids:
            mock_payload["document"] = {
                "filename": self.attachment_ids[0].name,
                "caption": (self.body or "")[:1024],
            }
        else:
            mock_payload["text"] = {"preview_url": True, "body": self.body or ""}

        mock_response = {
            "messaging_product": "whatsapp",
            "contacts": [{"input": self.phone, "wa_id": clean_digits}],
            "messages": [{"id": mock_wamid, "message_status": "accepted"}],
            "simulator_note": "Sandbox Simulator Mode: Execution verified successfully without external Meta billing."
        }

        self.write({
            'state': 'sent',
            'is_sandbox': True,
            'waba_message_id': mock_wamid,
            'payload': json.dumps(mock_payload, indent=2),
            'response': json.dumps(mock_response, indent=2),
            'error_message': False,
            'sent_date': fields.Datetime.now()
        })

        self._notify_origin_chatter(is_sandbox=True)

    def _upload_meta_media(self, api_url, phone_id, token, attachment):
        """Upload binary attachment to Meta Graph Media API and return media_id."""
        media_endpoint = f"{api_url}/{phone_id}/media"
        file_bytes = base64.b64decode(attachment.datas or b'')
        files = {
            'file': (attachment.name or 'document.pdf', file_bytes, attachment.mimetype or 'application/pdf')
        }
        data = {'messaging_product': 'whatsapp'}
        res = requests.post(
            media_endpoint,
            headers={'Authorization': f"Bearer {token}"},
            files=files,
            data=data,
            timeout=20
        )
        res_data = res.json()
        if res.status_code in (200, 201) and res_data.get('id'):
            return res_data['id'], None
        err = res_data.get('error', {})
        return None, f"Meta Media Upload Error ({res.status_code}): {err.get('message', res.text)}"

    def _process_live_meta_send(self, clean_digits):
        """Transmit message (template, free text, or PDF document) to Meta Graph API endpoint."""
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        api_url = ICP.get_param('whatsapp_cloud_api_engine.api_url', 'https://graph.facebook.com/v19.0').rstrip('/')
        phone_id = ICP.get_param('whatsapp_cloud_api_engine.phone_number_id')
        token = ICP.get_param('whatsapp_cloud_api_engine.access_token')

        if not phone_id or not token:
            msg = _('Missing Meta Phone Number ID or Access Token in Settings.')
            self.write({'state': 'failed', 'error_message': msg})
            return False

        headers = {
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }
        endpoint = f"{api_url}/{phone_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_digits,
        }

        try:
            if self.template_id and (self.use_meta_template or self.template_id.code == 'hello_world'):
                payload["type"] = "template"
                payload["template"] = {
                    "name": self.template_id.code,
                    "language": {"code": self.template_id.language}
                }
            elif self.attachment_ids:
                att = self.attachment_ids[0]
                media_id, media_err = self._upload_meta_media(api_url, phone_id, token, att)
                if media_err:
                    self.write({'state': 'failed', 'error_message': media_err})
                    return False
                payload["type"] = "document"
                payload["document"] = {
                    "id": media_id,
                    "filename": att.name or "document.pdf",
                    "caption": (self.body or "")[:1024]
                }
            else:
                payload["type"] = "text"
                payload["text"] = {"preview_url": True, "body": self.body or ""}

            self.write({'payload': json.dumps(payload, indent=2)})

            res = requests.post(endpoint, headers=headers, json=payload, timeout=15)
            res_data = res.json()
            res_str = json.dumps(res_data, indent=2)

            if res.status_code in (200, 201):
                messages = res_data.get('messages', [{}])
                wamid = messages[0].get('id', '')
                self.write({
                    'state': 'sent',
                    'is_sandbox': False,
                    'waba_message_id': wamid,
                    'response': res_str,
                    'error_message': False,
                    'sent_date': fields.Datetime.now()
                })
                self._notify_origin_chatter(is_sandbox=False)
                return True
            else:
                err = res_data.get('error', {})
                error_msg = f"Meta Error ({res.status_code}): {err.get('message', res.text)}"
                self.write({
                    'state': 'failed',
                    'response': res_str,
                    'error_message': error_msg
                })
                return False
        except requests.exceptions.RequestException as e:
            _logger.error("WhatsApp live dispatch failed: %s", str(e))
            self.write({
                'state': 'failed',
                'error_message': f"Network Connection Exception: {str(e)}"
            })
            return False

    def _notify_origin_chatter(self, is_sandbox=False):
        """Post informative audit trail badge into origin document chatter using safe Markup."""
        self.ensure_one()
        if not self.res_model or not self.res_id or self.res_model not in self.env:
            return

        target = self.env[self.res_model].sudo().browse(self.res_id)
        if target.exists() and hasattr(target, 'message_post'):
            if is_sandbox:
                tag = Markup('<span class="badge text-bg-warning" style="padding:2px 8px;border-radius:12px;font-size:11px;">[WhatsApp Sandbox]</span>')
            else:
                tag = Markup('<span class="badge text-bg-success" style="padding:2px 8px;border-radius:12px;font-size:11px;">[WhatsApp Live]</span>')

            body_html = Markup(
                '<div style="font-family:sans-serif;border-left:3px solid #25d366;padding-left:10px;">'
                '<p style="margin:0 0 4px 0;">{tag} <strong>WhatsApp Message Sent to {phone}</strong></p>'
                '<p style="margin:0 0 4px 0;color:#555;white-space:pre-wrap;">{body}</p>'
                '<small style="color:#888;">Ref: {ref} | Meta ID: {wamid}</small>'
                '</div>'
            ).format(
                tag=tag,
                phone=escape(self.phone or ''),
                body=escape(self.body or ''),
                ref=escape(self.name or ''),
                wamid=escape(self.waba_message_id or 'N/A'),
            )
            target.message_post(body=body_html, message_type='comment', subtype_xmlid='mail.mt_note')

    def action_simulate_delivered(self):
        """Simulate incoming Meta webhook delivery confirmation."""
        for rec in self:
            rec.write({'state': 'delivered'})
            rec.message_post(body=_("Simulated Webhook Event: Status updated to DELIVERED."))

    def action_simulate_read(self):
        """Simulate incoming Meta webhook blue-tick read receipt."""
        for rec in self:
            rec.write({'state': 'read'})
            rec.message_post(body=_("Simulated Webhook Event: Status updated to READ (Blue-tick verified)."))

    def action_retry(self):
        """Re-attempt dispatch for failed messages."""
        for rec in self:
            rec.retry_count += 1
            rec.action_send()

    @api.model
    def _cron_retry_failed_messages(self):
        """Cron: Re-attempt failed messages up to 3 retries."""
        failed_records = self.search([
            ('state', '=', 'failed'),
            ('retry_count', '<', 3),
            ('direction', '=', 'outbound')
        ], limit=50)
        for rec in failed_records:
            try:
                rec.action_retry()
            except Exception as e:
                _logger.warning("Cron retry failed for %s: %s", rec.name, str(e))

    @api.model
    def _cron_send_payment_reminders(self):
        """Cron: Identify overdue customer invoices and trigger WhatsApp alerts."""
        today = fields.Date.today()
        overdue_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('invoice_date_due', '<', today),
        ], limit=20)

        template = self.env.ref('whatsapp_cloud_api_engine.wa_template_payment_reminder', raise_if_not_found=False)
        if not template:
            return

        start_of_day = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for inv in overdue_invoices:
            if not inv.partner_id or not (inv.partner_id.phone or getattr(inv.partner_id, 'mobile', False)):
                continue

            already_sent = self.search_count([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', inv.id),
                ('template_id', '=', template.id),
                ('create_date', '>=', start_of_day)
            ])
            if already_sent == 0:
                inv._send_whatsapp_with_template(template)
