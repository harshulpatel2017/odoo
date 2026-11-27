# -*- coding: utf-8 -*-
import base64
import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class WhatsAppTemplate(models.Model):
    _name = 'whatsapp.template'
    _description = 'WhatsApp Message Template'
    _order = 'name asc'

    name = fields.Char(string='Template Title', required=True)
    code = fields.Char(
        string='Meta Template Identifier', required=True, copy=False,
        help='Unique identifier name configured in Meta WhatsApp Manager (e.g. sales_order_confirmation)'
    )
    category = fields.Selection([
        ('utility', 'Utility (Transactional)'),
        ('marketing', 'Marketing / Promotions'),
        ('authentication', 'Authentication / OTP')
    ], string='Category', default='utility', required=True)
    language = fields.Selection([
        ('en_US', 'English (US)'),
        ('en_GB', 'English (UK)'),
        ('gu_IN', 'Gujarati (India)'),
        ('hi_IN', 'Hindi (India)'),
        ('ar_SA', 'Arabic'),
    ], string='Language', default='en_US', required=True)
    model_id = fields.Many2one('ir.model', string='Applies to Model', required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', string='Model Name', readonly=True, store=True)
    body = fields.Text(
        string='Message Body', required=True,
        help='Template text supporting dynamic parameters e.g. {{partner_name}}, {{amount_total}}, {{order_name}}'
    )
    header_type = fields.Selection([
        ('none', 'None (Standard Text)'),
        ('text', 'Text Header'),
        ('document', 'Document (PDF Attachment)'),
        ('image', 'Image Header')
    ], string='Header Type', default='none', required=True)
    header_text = fields.Char(string='Header Text')
    report_id = fields.Many2one(
        'ir.actions.report', string='PDF Report to Attach',
        domain="[('model', '=', model_name)]",
        help='QWeb report that will be rendered into PDF and sent along with WhatsApp message'
    )
    active = fields.Boolean(string='Active', default=True)

    def render_body(self, record):
        """Render template body with dynamic record values."""
        self.ensure_one()
        text = self.body or ''
        if not record:
            return text

        company = getattr(record, 'company_id', self.env.company)
        currency = getattr(record, 'currency_id', company.currency_id)
        partner = getattr(record, 'partner_id', False)

        amount_total = getattr(record, 'amount_total', 0.0)
        formatted_total = f"{currency.symbol} {amount_total:,.2f}" if currency else f"{amount_total:,.2f}"

        amount_residual = getattr(record, 'amount_residual', 0.0)
        formatted_residual = f"{currency.symbol} {amount_residual:,.2f}" if currency else f"{amount_residual:,.2f}"

        due_date = str(getattr(record, 'invoice_date_due', '') or getattr(record, 'date_order', '') or '')
        scheduled_date = str(getattr(record, 'scheduled_date', '') or '')[:10]

        item_count = 0
        if hasattr(record, 'move_ids'):
            item_count = len(record.move_ids)
        elif hasattr(record, 'move_ids_without_package'):
            item_count = len(record.move_ids_without_package)
        elif hasattr(record, 'order_line'):
            item_count = len(record.order_line)

        replacements = {
            '{{partner_name}}': partner.name if partner else 'Customer',
            '{{company_name}}': company.name or 'Our Company',
            '{{order_name}}': record.display_name or '',
            '{{invoice_name}}': record.display_name or '',
            '{{picking_name}}': record.display_name or '',
            '{{origin}}': getattr(record, 'origin', '') or getattr(record, 'name', '') or '',
            '{{amount_total}}': formatted_total,
            '{{amount_residual}}': formatted_residual,
            '{{due_date}}': due_date,
            '{{scheduled_date}}': scheduled_date,
            '{{payment_state}}': str(getattr(record, 'payment_state', 'not_paid')).replace('_', ' ').title(),
            '{{item_count}}': str(item_count or 1),
        }

        for placeholder, val in replacements.items():
            text = text.replace(placeholder, str(val))

        return text

    def generate_attachment(self, record):
        """Generate PDF attachment from report_id if configured."""
        self.ensure_one()
        if self.header_type != 'document':
            return False

        report = self.report_id
        if not report:
            if self.model_name == 'sale.order':
                report = self.env.ref('sale.action_report_saleorder', raise_if_not_found=False)
            elif self.model_name == 'account.move':
                report = self.env.ref('account.account_invoices', raise_if_not_found=False)
            elif self.model_name == 'stock.picking':
                report = self.env.ref('stock.action_report_delivery', raise_if_not_found=False)

        if not report:
            _logger.warning("No PDF report found for template %s on %s", self.name, self.model_name)
            return False

        try:
            pdf_content, _format = self.env['ir.actions.report']._render_qweb_pdf(
                report.id, res_ids=[record.id]
            )
            filename = f"{(record.display_name or 'document').replace('/', '_')}.pdf"
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': record._name,
                'res_id': record.id,
                'mimetype': 'application/pdf'
            })
            return attachment
        except Exception as e:
            _logger.error("Failed to render QWeb PDF for %s: %s", record.display_name, str(e))
            return False
