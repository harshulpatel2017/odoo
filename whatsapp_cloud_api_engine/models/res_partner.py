# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    whatsapp_number = fields.Char(
        string='WhatsApp Number',
        compute='_compute_whatsapp_number',
        store=True,
        readonly=False,
        help='Sanitized international E.164 phone number without spaces, hyphens or special symbols (e.g. +919876543210)'
    )

    @api.depends('phone', 'country_id')
    def _compute_whatsapp_number(self):
        for partner in self:
            raw_phone = partner.phone or getattr(partner, 'mobile', '') or ''
            partner.whatsapp_number = partner._sanitize_whatsapp_phone(raw_phone)

    def _sanitize_whatsapp_phone(self, phone):
        """Sanitize phone string to digits and leading +."""
        if not phone:
            return False
        clean = re.sub(r'[^0-9+]', '', str(phone).strip())
        if clean.startswith('00'):
            clean = '+' + clean[2:]
        elif not clean.startswith('+') and self.country_id and self.country_id.phone_code:
            # Default country code if missing
            clean = f"+{self.country_id.phone_code}{clean.lstrip('0')}"
        elif not clean.startswith('+'):
            # Default to India (+91) if 10-digit number
            if len(clean) == 10:
                clean = f"+91{clean}"
            else:
                clean = f"+{clean}"
        return clean

    def action_open_whatsapp_chat(self):
        """Quick action to open WhatsApp web chat in browser."""
        self.ensure_one()
        raw_phone = self.phone or getattr(self, 'mobile', '')
        phone = self.whatsapp_number or self._sanitize_whatsapp_phone(raw_phone)
        if not phone:
            raise UserError(_('Please configure a valid phone number for %s.') % self.name)
        digits_only = re.sub(r'[^0-9]', '', phone)
        url = f"https://wa.me/{digits_only}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }
