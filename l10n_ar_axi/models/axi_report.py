from odoo import api, fields, models, _
from odoo.exceptions import UserError
import base64
import calendar
import io
import xlsxwriter
from datetime import date, timedelta


class AxiReport(models.TransientModel):
    _name = 'axi.report'
    _description = 'Reporte Sumas y Saldos Comparativo AXI'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    date_to = fields.Date(string='Fecha de corte', required=True)
    journal_ids = fields.Many2many(
        'account.journal', string='Diarios a incluir',
        domain="[('company_id', '=', company_id)]",
    )

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Precarga diarios: todos menos el de ajuste AXI y los excluidos por configuracion."""
        if not self.company_id:
            return
        axi_journal = self.company_id.axi_journal_id
        excluded = self.company_id.axi_excluded_journal_ids
        excluded_ids = excluded.ids + ([axi_journal.id] if axi_journal else [])
        domain = [('company_id', '=', self.company_id.id)]
        if excluded_ids:
            domain.append(('id', 'not in', excluded_ids))
        self.journal_ids = self.env['account.journal'].search(domain)

    def _get_fiscal_year_start(self, company, date_end):
        """Calcula el inicio del ejercicio fiscal. Reutilizado de axi.batch."""
        fy_month = int(company.fiscalyear_last_month or 12)
        last_day_of_month = calendar.monthrange(date_end.year, fy_month)[1]
        fy_day = min(int(company.fiscalyear_last_day or 31), last_day_of_month)
        fy_end_this = date(date_end.year, fy_month, fy_day)
        if date_end > fy_end_this:
            return fy_end_this + timedelta(days=1)
        last_day_prev = calendar.monthrange(date_end.year - 1, fy_month)[1]
        fy_day_prev = min(fy_day, last_day_prev)
        fy_end_prev = date(date_end.year - 1, fy_month, fy_day_prev)
        return fy_end_prev + timedelta(days=1)

    def action_export_xlsx(self):
        self.ensure_one()
        if not self.journal_ids:
            raise UserError(_('Seleccioná al menos un diario.'))

        axi_journal = self.company_id.axi_journal_id
        all_journal_ids = self.journal_ids.ids
        # Ajustado = diarios seleccionados + diario AXI (si está configurado)
        ajustado_journal_ids = list(set(all_journal_ids + ([axi_journal.id] if axi_journal else [])))

        # Inicio del ejercicio fiscal
        fiscal_start = self._get_fiscal_year_start(self.company_id, self.date_to)

        # Saldos históricos (sin diario AXI, desde inicio del ejercicio)
        historico = self._get_balances(all_journal_ids, fiscal_start)
        # Saldos ajustados (con diario AXI, desde inicio del ejercicio)
        ajustado = self._get_balances(ajustado_journal_ids, fiscal_start)

        # Unión de cuentas ordenadas por código
        all_accounts = sorted(
            set(historico.keys()) | set(ajustado.keys()),
            key=lambda a: a.code or ''
        )

        # Generar XLSX
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('SyS Comparativo')

        # Formatos
        fmt_title = wb.add_format({'bold': True, 'font_size': 13})
        fmt_sub = wb.add_format({'italic': True, 'font_color': '#555555'})
        fmt_header = wb.add_format({
            'bold': True, 'bg_color': '#2E4057', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter',
        })
        fmt_account = wb.add_format({'border': 1})
        fmt_number = wb.add_format({'border': 1, 'num_format': '#,##0.00'})
        fmt_diff_pos = wb.add_format({'border': 1, 'num_format': '#,##0.00', 'font_color': '#1a7a4a'})
        fmt_diff_neg = wb.add_format({'border': 1, 'num_format': '#,##0.00', 'font_color': '#c0392b'})
        fmt_zero = wb.add_format({'border': 1, 'num_format': '#,##0.00', 'font_color': '#888888'})

        # Título
        ws.merge_range('A1:E1', 'Sumas y Saldos Comparativo — Ajuste por Inflación', fmt_title)
        ws.write('A2', f'Compañía: {self.company_id.name}', fmt_sub)
        ws.write('A3', f'Período: {fiscal_start} al {self.date_to}', fmt_sub)

        # Encabezados
        row = 4
        ws.set_column('A:A', 16)
        ws.set_column('B:B', 45)
        ws.set_column('C:E', 22)
        headers = ['Cuenta', 'Descripción', 'Saldo Histórico', 'Saldo Ajustado', 'Diferencia']
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_header)
        row += 1

        for account in all_accounts:
            hist = historico.get(account, 0.0)
            ajus = ajustado.get(account, 0.0)
            diff = ajus - hist

            ws.write(row, 0, account.code or '', fmt_account)
            ws.write(row, 1, account.name or '', fmt_account)
            ws.write(row, 2, hist, fmt_number)
            ws.write(row, 3, ajus, fmt_number)

            if diff > 0:
                ws.write(row, 4, diff, fmt_diff_pos)
            elif diff < 0:
                ws.write(row, 4, diff, fmt_diff_neg)
            else:
                ws.write(row, 4, diff, fmt_zero)
            row += 1

        wb.close()
        output.seek(0)
        xlsx_data = output.read()

        attachment = self.env['ir.attachment'].create({
            'name': f'SyS_Comparativo_{self.date_to}.xlsx',
            'datas': base64.b64encode(xlsx_data).decode('utf-8'),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _get_balances(self, journal_ids, date_from):
        """Devuelve dict {account: saldo} para los diarios y rango de fechas dados."""
        if not journal_ids:
            return {}
        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('journal_id', 'in', journal_ids),
            ('parent_state', '=', 'posted'),
            ('date', '>=', date_from),
            ('date', '<=', self.date_to),
        ])
        balances = {}
        for line in lines:
            acc = line.account_id
            balances[acc] = balances.get(acc, 0.0) + line.balance
        return balances
