# -*- coding: utf-8 -*-
import json
import logging
from odoo import http, fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class WhatsAppWebhookController(http.Controller):

    @http.route('/whatsapp/webhook', type='http', auth='public', methods=['GET'], csrf=False)
    def verify_webhook(self, **kwargs):
        """Handle Meta Webhook challenge verification."""
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')

        ICP = request.env['ir.config_parameter'].sudo()
        expected_token = ICP.get_param('whatsapp_cloud_api_engine.webhook_verify_token', 'odoo19_whatsapp_secure_token')

        if mode == 'subscribe' and token == expected_token:
            _logger.info("WhatsApp Webhook verified successfully by Meta challenge.")
            return Response(challenge or '', status=200, content_type='text/plain')
        _logger.warning("WhatsApp Webhook verification rejected: Invalid token %s", token)
        return Response("Verification failed", status=403)

    @http.route('/whatsapp/webhook', type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def receive_webhook_event(self):
        """Handle incoming Meta status notifications (delivered, read, failed) and inbound messages."""
        try:
            data = json.loads(request.httprequest.data or b'{}')
        except Exception:
            data = {}

        entry_list = data.get('entry', [])
        for entry in entry_list:
            for change in entry.get('changes', []):
                value = change.get('value', {})

                statuses = value.get('statuses', [])
                for status_event in statuses:
                    wamid = status_event.get('id')
                    status_name = status_event.get('status')
                    if wamid and status_name:
                        self._update_message_status(wamid, status_name, status_event)

                incoming_messages = value.get('messages', [])
                for msg in incoming_messages:
                    self._process_inbound_message(msg, value.get('contacts', []))

        return {'status': 'processed'}

    def _update_message_status(self, wamid, status_name, event_data):
        """Update local message log according to Meta delivery status."""
        log = request.env['whatsapp.message.log'].sudo().search([('waba_message_id', '=', wamid)], limit=1)
        if not log:
            return

        state_mapping = {
            'sent': 'sent',
            'delivered': 'delivered',
            'read': 'read',
            'failed': 'failed',
        }
        new_state = state_mapping.get(status_name)
        if new_state and log.state != 'read':
            vals = {'state': new_state}
            if new_state == 'failed':
                errors = event_data.get('errors', [{}])
                vals['error_message'] = errors[0].get('title', 'Unknown Meta delivery failure')
            log.write(vals)
            _logger.info("Updated WhatsApp Message %s to status %s via Meta Webhook", log.name, new_state)

    def _process_inbound_message(self, msg, contacts):
        """Record inbound reply from customer into message log."""
        sender_phone = msg.get('from', '')
        msg_type = msg.get('type', 'text')
        text_body = msg.get('text', {}).get('body', '') if msg_type == 'text' else f"[{msg_type.upper()} Attachment]"
        wamid = msg.get('id')

        clean_phone = f"+{sender_phone}" if sender_phone and not sender_phone.startswith('+') else sender_phone
        partner = False
        if sender_phone:
            partner = request.env['res.partner'].sudo().search([
                '|', ('phone', 'ilike', sender_phone[-10:]),
                ('whatsapp_number', 'ilike', sender_phone[-10:])
            ], limit=1)

        request.env['whatsapp.message.log'].sudo().create({
            'partner_id': partner.id if partner else False,
            'phone': clean_phone,
            'direction': 'inbound',
            'message_type': 'text',
            'body': text_body,
            'waba_message_id': wamid,
            'state': 'delivered',
            'sent_date': fields.Datetime.now()
        })
        _logger.info("Inbound WhatsApp message logged from %s", clean_phone)
