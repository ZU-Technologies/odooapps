# -*- coding: utf-8 -*-

import base64
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    country_code = fields.Char(related='company_id.country_id.code', readonly=True)
    l10n_sa_delivery_date = fields.Date(string='Delivery Date', default=fields.Date.context_today, copy=False)
    l10n_sa_show_delivery_date = fields.Boolean(compute='_compute_show_delivery_date')
    l10n_sa_qr_code_str = fields.Char(string='Zatka QR Code', compute='_compute_qr_code_str')
    l10n_sa_confirmation_datetime = fields.Datetime(string='Confirmation Date', readonly=True, copy=False)

    def to_bytes(self, n, length, byteorder='big'):
        h = '%x' % int(n)
        s = ('0' * (len(h) % 2) + h).zfill(length * 2).decode('hex')
        return s if byteorder == 'big' else s[::-1]

    @api.depends('country_code', 'type')
    def _compute_show_delivery_date(self):
        for rec in self:
            rec.l10n_sa_show_delivery_date = rec.country_code == 'SA' and rec.type in ('out_invoice', 'out_refund')

    @api.depends('amount_total', 'amount_untaxed', 'l10n_sa_confirmation_datetime', 'company_id', 'company_id.vat')
    def _compute_qr_code_str(self):
        """ Generate the qr code for Saudi e-invoicing. Specs are available at the following link at page 23
        https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20210528_ZATCA_Electronic_Invoice_Security_Features_Implementation_Standards_vShared.pdf
        """
        def get_qr_encoding(tag, field):
            company_name_byte_array = field.encode('UTF-8')
            company_name_tag_encoding = self.to_bytes(tag, 1, 'big')
            company_name_length_encoding = self.to_bytes(len(company_name_byte_array), 1, 'big')
            return company_name_tag_encoding + company_name_length_encoding + company_name_byte_array

        for record in self:
            qr_code_str = ''
            if record.l10n_sa_confirmation_datetime and record.company_id.vat:
                seller_name_enc = get_qr_encoding('1', record.company_id.display_name)
                company_vat_enc = get_qr_encoding('2', record.company_id.vat)
                time_sa = fields.Datetime.context_timestamp(self.with_context(tz='Asia/Riyadh'), fields.Datetime.from_string(record.l10n_sa_confirmation_datetime))
                timestamp_enc = get_qr_encoding('3', time_sa.isoformat())
                invoice_total_enc = get_qr_encoding('4', str(record.amount_total))
                total_vat_enc = get_qr_encoding('5', str(record.currency_id.round(record.amount_total - record.amount_untaxed)))

                str_to_encode = seller_name_enc + company_vat_enc + timestamp_enc + invoice_total_enc + total_vat_enc
                qr_code_str = base64.b64encode(str_to_encode).decode('UTF-8')
            record.l10n_sa_qr_code_str = qr_code_str

    def action_invoice_open(self):
        res = super(AccountInvoice, self).action_invoice_open()
        for record in self:
            if record.country_code == 'SA' and record.type in ('out_invoice', 'out_refund'):
                if not record.l10n_sa_show_delivery_date:
                    raise UserError(_('Delivery Date cannot be empty'))
                if record.l10n_sa_delivery_date < record.date_invoice:
                    raise UserError(_('Delivery Date cannot be before Invoice Date'))
                self.write({
                    'l10n_sa_confirmation_datetime': fields.Datetime.now()
                })
        return res