# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

"""
Partner Time to Pay - Res Partner Model Extension

This module extends the res.partner model to calculate and store
statistics regarding Days to Pay (D2P) and Days to Receive (D2R).
It computes averages for lifetime and Year-To-Date (YTD) periods
based on paid invoices and their associated payment dates.
"""

from datetime import datetime, timedelta, timezone

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    d2p_life = fields.Float(
        compute="_compute_d2x",
        string="AVG Days to Payable (lifetime)",
    )
    d2p_ytd = fields.Float(compute="_compute_d2x", string="AVG Days to Payable (YTD)")
    d2r_life = fields.Float(
        compute="_compute_d2x", string="AVG Days to Receivable (lifetime)"
    )
    d2r_ytd = fields.Float(
        compute="_compute_d2x", string="AVG Days to Receivable (YTD)"
    )

    def _compute_d2x(self):
        """Compute D2P and D2R statistics for each partner."""
        for partner in self:
            partner.d2p_ytd, partner.d2p_life = self._compute_d2x_per_invoice_type(
                partner, "out_invoice"
            )
            partner.d2r_ytd, partner.d2r_life = self._compute_d2x_per_invoice_type(
                partner, "in_invoice"
            )

    def _compute_d2x_per_invoice_type(self, partner, invoice_type):
        """
        Calculate average days to pay/receive for a specific invoice type.

        :param partner: The partner record to compute stats for.
        :param invoice_type: The move type ('out_invoice' or 'in_invoice').
        :return: Tuple of (ytd_avg, lifetime_avg) floats.
        """
        # Odoo 19+: Use timezone-aware datetime for robustness
        this_year = datetime.now(timezone.utc).year

        total_number_of_invoices_life = 0
        total_number_of_invoices_ytd = 0

        total_days_to_pay_life = 0
        total_days_to_pay_ytd = 0

        d2x_ytd = 0
        d2x_life = 0

        # Fetch invoices directly using the model environment
        invoices = self.env["account.move"].search(
            [
                ("partner_id", "=", partner.id),
                ("payment_state", "=", "paid"),
                ("move_type", "=", invoice_type),
            ]
        )

        for invoice in invoices:
            # Odoo 19+: account.move uses 'payment_move_line_ids' or similar
            # depending on version, but _get_reconciled_payments is a common helper
            # in enterprise/account modules. If this helper is missing in community,
            # we might need to adjust, but assuming standard API compatibility for
            # this module context.
            payment_ids = invoice._get_reconciled_payments()
            
            # Odoo 17+: invoice_date is standard. Ensure it's a date object.
            date_due = invoice.invoice_date
            if not date_due:
                continue
                
            invoice_year = date_due.year

            days_to_pay_invoice = self._get_invoice_payment(payment_ids, date_due)
            total_number_of_invoices_life += 1

            total_days_to_pay_life += days_to_pay_invoice

            if invoice_year == this_year:
                total_number_of_invoices_ytd += 1
                total_days_to_pay_ytd += days_to_pay_invoice

        if total_number_of_invoices_ytd != 0:
            d2x_ytd = total_days_to_pay_ytd / total_number_of_invoices_ytd
        else:
            d2x_ytd = 0

        if total_number_of_invoices_life != 0:
            d2x_life = total_days_to_pay_life / total_number_of_invoices_life
        else:
            d2x_life = 0

        return d2x_ytd, d2x_life

    def _get_invoice_ids(self, partner_id, invoice_type):
        """
        Retrieve paid invoices for a partner of a specific type.
        
        Note: This method is kept for backward compatibility if called elsewhere,
        but _compute_d2x_per_invoice_type now queries directly.
        """
        return self.env["account.move"].search(
            [
                ("partner_id", "=", partner_id),
                ("payment_state", "=", "paid"),
                ("move_type", "=", invoice_type),
            ]
        )

    # payment is a model of account.move
    def _get_invoice_payment(self, payment_time_ids, date_due):
        """
        Calculate the maximum days between due date and payment date.

        :param payment_time_ids: Recordset of payment moves/lines.
        :param date_due: The due date of the invoice.
        :return: Integer days to pay.
        """
        days_for_latest_payment = 0
        for payment in payment_time_ids:
            if payment.state == "posted":
                # Ensure payment date is a date object
                payment_date = payment.date
                if not payment_date:
                    continue
                    
                days_for_this_payment = (payment_date - date_due).days
                if days_for_this_payment < 0:
                    days_for_this_payment = 0
                if days_for_this_payment > days_for_latest_payment:
                    days_for_latest_payment = days_for_this_payment
        return days_for_latest_payment