# -*- coding: utf-8 -*-
{
    'name': 'WhatsApp Cloud API & Automated Messaging Engine',
    'version': '19.0.1.0.0',
    'category': 'Marketing/Automation',
    'summary': 'Meta Official WhatsApp Cloud API Integration, Automated PDF Invoicing, Sales Confirmations & Sandbox Simulation Engine',
    'description': """
WhatsApp Cloud API & Automated Messaging Engine (Odoo 19)
=========================================================
Enterprise-ready, Meta-approved WhatsApp Cloud API connector with zero-overhead sandbox simulation,
automated document dispatch (Sales, Invoices, Deliveries), dynamic template mapping, and bi-directional audit logging.

Key Highlights:
---------------
* **Official Meta Cloud API:** Direct HTTP/2 integration with Graph API v19.0+ without costly third-party aggregator subscriptions (Twilio/Wati).
* **Dual Execution Mode:**
    - *Live Cloud Mode:* Instant real-world message and PDF delivery to customer devices.
    - *Sandbox / Simulator Mode:* Test out-of-the-box without needing any Meta credentials; simulates JSON payloads, delivery status, and chatter notifications.
* **Automated Workflow Triggers:**
    - Auto-send branded WhatsApp notification upon Sales Order Confirmation.
    - Auto-send Customer Invoice with high-resolution QWeb PDF attachment upon Posting.
    - Auto-send Delivery Tracking & Dispatch confirmation upon Stock Transfer validation.
* **Interactive WhatsApp Composer Wizard:**
    - Live chat bubble preview inside Odoo modal.
    - Dynamic placeholder evaluation (Partner name, amount, dates, currency).
    - One-click attachment rendering.
* **Central Message Audit Log (whatsapp.message.log):**
    - Full bi-directional tracking (Draft -> Queued -> Sent -> Delivered -> Read -> Failed).
    - Raw JSON request/response inspector for technical audits.
    - Resend queue and retry mechanism for transient network failures.
* **Webhook Receiver:**
    - Handles incoming Meta status updates (Delivered, Read, Failed) and inbound replies.
    - Zero core monkey-patching, upgrade-safe, multi-company compliant.
    """,
    'author': 'Harshul Patel',
    'website': 'https://harshul-patel-portfolio.vercel.app',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'sale',
        'account',
        'stock',
    ],
    'data': [
        # Security
        'security/whatsapp_security.xml',
        'security/ir.model.access.csv',

        # Data & Sequences
        'data/ir_sequence_data.xml',
        'data/whatsapp_template_data.xml',
        'data/ir_cron_data.xml',

        # Wizards
        'wizard/whatsapp_composer_views.xml',

        # Views
        'views/whatsapp_template_views.xml',
        'views/whatsapp_message_log_views.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/stock_picking_views.xml',
        'views/res_partner_views.xml',
        'views/whatsapp_menu_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
