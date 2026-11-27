# -*- coding: utf-8 -*-
import requests
import logging
from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    whatsapp_api_url = fields.Char(
        string='Meta Graph API URL',
        config_parameter='whatsapp_cloud_api_engine.api_url',
        default='https://graph.facebook.com/v19.0',
        help='Meta Graph API base endpoint (default: https://graph.facebook.com/v19.0)'
    )
    whatsapp_phone_number_id = fields.Char(
        string='Phone Number ID',
        config_parameter='whatsapp_cloud_api_engine.phone_number_id',
        help='Unique Phone Number ID assigned by Meta WhatsApp Cloud API console'
    )
    whatsapp_account_id = fields.Char(
        string='WABA Account ID',
        config_parameter='whatsapp_cloud_api_engine.account_id',
        help='WhatsApp Business Account (WABA) ID'
    )
    whatsapp_access_token = fields.Char(
        string='Permanent Access Token',
        config_parameter='whatsapp_cloud_api_engine.access_token',
        help='System User permanent access token generated from Meta Business Manager'
    )
    whatsapp_webhook_verify_token = fields.Char(
        string='Webhook Verify Token',
        config_parameter='whatsapp_cloud_api_engine.webhook_verify_token',
        default='odoo19_whatsapp_secure_token',
        help='Arbitrary secret string entered into Meta Webhook configuration for signature verification'
    )
    whatsapp_sandbox_mode = fields.Boolean(
        string='Enable Sandbox Simulator Mode',
        config_parameter='whatsapp_cloud_api_engine.sandbox_mode',
        help='When enabled, WhatsApp messages and payloads are simulated internally without calling live Meta servers. Perfect for development, demonstration, and offline testing.'
    )
    whatsapp_auto_send_sale = fields.Boolean(
        string='Auto-Send on Order Confirmation',
        config_parameter='whatsapp_cloud_api_engine.auto_send_sale',
        help='Automatically trigger WhatsApp confirmation to customer upon sales order validation'
    )
    whatsapp_auto_send_invoice = fields.Boolean(
        string='Auto-Send on Invoice Post',
        config_parameter='whatsapp_cloud_api_engine.auto_send_invoice',
        help='Automatically send PDF invoice to customer WhatsApp upon posting invoice'
    )
    whatsapp_auto_send_delivery = fields.Boolean(
        string='Auto-Send on Delivery Transfer',
        config_parameter='whatsapp_cloud_api_engine.auto_send_delivery',
        help='Automatically send delivery dispatch alert upon picking validation'
    )

    def action_test_whatsapp_connection(self):
        """Test the connection with Meta WhatsApp Cloud API or verify sandbox simulator."""
        self.ensure_one()
        is_sandbox = self.whatsapp_sandbox_mode or (
            self.env['ir.config_parameter'].sudo().get_param(
                'whatsapp_cloud_api_engine.sandbox_mode', 'False'
            ) == 'True'
        )

        if is_sandbox and self.whatsapp_sandbox_mode:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sandbox Simulator Active!'),
                    'message': _('WhatsApp Engine is running in Simulation Sandbox mode. Messages and payloads will be logged with full audit traces without requiring live Meta credentials.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        api_url = self.whatsapp_api_url or 'https://graph.facebook.com/v19.0'
        phone_id = self.whatsapp_phone_number_id
        token = self.whatsapp_access_token

        if not phone_id or not token:
            raise UserError(_('Please provide both Phone Number ID and Meta Access Token before running connection test.'))

        endpoint = f"{api_url.rstrip('/')}/{phone_id}"
        headers = {
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }

        try:
            response = requests.get(endpoint, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                display_phone = data.get('display_phone_number', phone_id)
                verified_name = data.get('verified_name', 'Verified Business')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful!'),
                        'message': _('Successfully connected to Meta WhatsApp Cloud API! Verified Name: %s (%s)') % (verified_name, display_phone),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                err_json = response.json().get('error', {})
                err_msg = err_json.get('message', response.text)
                raise UserError(_('Meta WhatsApp API Error (%s): %s') % (response.status_code, err_msg))
        except requests.exceptions.RequestException as e:
            _logger.error("WhatsApp API connection failed: %s", str(e))
            raise UserError(_('Network / Connection failed: %s') % str(e))
