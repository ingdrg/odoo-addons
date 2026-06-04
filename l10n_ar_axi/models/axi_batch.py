import calendar
from collections import defaultdict
from datetime import date, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AxiBatch(models.Model):
    _name = 'axi.batch'
    _description = 'Batch Ajuste por Inflación'
    _order = 'date_end desc, id desc'

    name = fields.Char(required=True, copy=False, default=lambda self: _('Nuevo'))
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)
    date_end = fields.Date(string='Fecha de cierre', required=True)
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario',
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        default=lambda self: self.env.company.axi_journal_id or False,
    )

    move_id = fields.Many2one('account.move', copy=False, readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('posted', 'Asentado'),
    ], default='draft')
    result_ids = fields.One2many('axi.result', 'batch_id', string='Resultados', readonly=True)
    line_count = fields.Integer(string='Cuentas ajustadas', compute='_compute_line_count')
    currency_id = fields.Many2one(related='company_id.currency_id')
    close_index_id = fields.Many2one('axi.index', string='Índice de cierre', compute='_compute_close_index_id', store=False)
    close_index_value = fields.Float(string='Valor índice de cierre', compute='_compute_close_index_id', digits=(16, 6), store=False)
    note = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('axi.batch') or _('Nuevo')
        return super().create(vals_list)

    @api.depends('result_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.result_ids)

    @api.depends('date_end')
    def _compute_close_index_id(self):
        Index = self.env['axi.index']
        for rec in self:
            rec.close_index_id = False
            rec.close_index_value = 0.0
            if rec.date_end:
                month_end = fields.Date.end_of(rec.date_end, 'month')
                idx = Index.search([('date', '=', month_end)], limit=1)
                rec.close_index_id = idx
                rec.close_index_value = idx.index_value if idx else 0.0

    def _get_fiscal_year_start(self, company, date_end):
        """
        Calcula el inicio del ejercicio fiscal vigente.
        Usa calendar.monthrange para evitar fechas invalidas (ej: 31/feb).
        """
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

    def _get_month_end(self, dt):
        return fields.Date.end_of(dt, 'month')

    def _preload_indices(self, journal_items):
        """
        Pre-carga todos los indices IPC necesarios para las fechas de los apuntes.
        Evita N+1 queries en el loop de calculo.
        Devuelve un dict {date: axi.index record} y lanza UserError si falta alguno.
        """
        dates_needed = set(
            fields.Date.end_of(line.date, 'month') for line in journal_items
        )
        indices = self.env['axi.index'].search([('date', 'in', list(dates_needed))])
        index_by_date = {idx.date: idx for idx in indices}
        missing = sorted(d for d in dates_needed if d not in index_by_date)
        if missing:
            raise UserError(
                _('Faltan indices IPC para los siguientes meses:\n%s')
                % '\n'.join(str(d) for d in missing)
            )
        return index_by_date

    def _get_ipc_for_date(self, dt, index_by_date=None):
        """
        Devuelve el indice IPC para el fin de mes de dt.
        Si se pasa index_by_date (dict precargado), lo usa directamente.
        """
        month_end = self._get_month_end(dt)
        if index_by_date is not None:
            idx = index_by_date.get(month_end)
            if not idx:
                raise UserError(
                    _('No hay IPC cargado para el mes de %(date)s (se esperaba fecha %(month_end)s).')
                    % {'date': dt, 'month_end': month_end}
                )
            return idx
        idx = self.env['axi.index'].search([('date', '=', month_end)], limit=1)
        if not idx:
            raise UserError(
                _('No hay IPC cargado para el mes de %(date)s (se esperaba fecha %(month_end)s).')
                % {'date': dt, 'month_end': month_end}
            )
        if idx.index_value <= 0:
            raise UserError(_('El IPC para %s debe ser mayor que cero.') % month_end)
        return idx

    def _get_non_monetary_accounts(self):
        self.ensure_one()
        tag = self.company_id.axi_non_monetary_tag_id
        if not tag:
            raise UserError(_('Configurá la etiqueta de cuentas no monetarias en Ajustes de Contabilidad.'))
        # v15: account.account usa company_id (Many2one) y existe el campo deprecated
        accounts = self.env['account.account'].search([
            ('company_id', '=', self.company_id.id),
            ('deprecated', '=', False),
            ('tag_ids', 'in', tag.id),
        ])
        if not accounts:
            raise UserError(
                _('No hay cuentas con la etiqueta %(tag)s para la compañia %(company)s.')
                % {'tag': tag.display_name, 'company': self.company_id.display_name}
            )
        return accounts

    def _build_move_lines(self, deltas_by_account):
        self.ensure_one()
        recpam_account = self.company_id.axi_recpam_account_id
        if not recpam_account:
            raise UserError(_('Configurá la cuenta RECPAM en Ajustes de Contabilidad.'))

        lines = []
        for account, delta in deltas_by_account.items():
            if self.company_id.currency_id.is_zero(delta):
                continue
            lines.append((0, 0, {
                'account_id': account.id,
                'name': _('Ajuste por inflación %s') % self.name,
                'debit': delta if delta > 0 else 0.0,
                'credit': -delta if delta < 0 else 0.0,
            }))
            lines.append((0, 0, {
                'account_id': recpam_account.id,
                'name': _('RECPAM %s') % account.display_name,
                'debit': -delta if delta < 0 else 0.0,
                'credit': delta if delta > 0 else 0.0,
            }))
        if not lines:
            raise UserError(_('No hay líneas con ajuste material para contabilizar.'))
        return lines

    def action_calculate_and_post(self):
        move_to_open = False
        for batch in self:
            if batch.state == 'posted' and batch.move_id:
                raise UserError(_('El batch %s ya fue contabilizado.') % batch.display_name)
            if not batch.company_id or not batch.date_end or not batch.journal_id:
                raise UserError(_('Faltan datos obligatorios: compañia, fecha de cierre o diario.'))

            # Savepoint: si algo falla, el estado del batch queda intacto
            with self.env.cr.savepoint():
                close_index = batch._get_ipc_for_date(batch.date_end)
                fiscal_start = batch._get_fiscal_year_start(batch.company_id, batch.date_end)
                accounts = batch._get_non_monetary_accounts()

                # Limpiar resultados y asiento previo solo si el calculo puede continuar
                if batch.move_id:
                    if batch.move_id.state == 'posted':
                        batch.move_id.button_draft()
                    # v15: un asiento que estuvo posteado requiere force_delete para eliminarse
                    batch.move_id.with_context(force_delete=True).unlink()
                batch.result_ids.unlink()

                journal_items = self.env['account.move.line'].search([
                    ('company_id', '=', batch.company_id.id),
                    ('account_id', 'in', accounts.ids),
                    ('parent_state', '=', 'posted'),
                    ('date', '>=', fiscal_start),
                    ('date', '<=', batch.date_end),
                ], order='date asc, id asc')

                # Pre-cargar todos los indices necesarios (evita N+1 queries)
                index_by_date = batch._preload_indices(journal_items)

                base_by_account = defaultdict(float)
                delta_by_account = defaultdict(float)

                for line in journal_items:
                    base = line.balance
                    if batch.company_id.currency_id.is_zero(base):
                        continue
                    line_index = batch._get_ipc_for_date(line.date, index_by_date)
                    coef = close_index.index_value / line_index.index_value
                    reexpressed = base * coef
                    delta = reexpressed - base
                    base_by_account[line.account_id] += base
                    delta_by_account[line.account_id] += delta

                results_to_create = []
                for account, base in base_by_account.items():
                    delta = delta_by_account.get(account, 0.0)
                    monto_ajustado = base + delta
                    # Coeficiente promedio ponderado (informativo)
                    coef_aplicado = (monto_ajustado / base) if not batch.company_id.currency_id.is_zero(base) else 1.0
                    results_to_create.append({
                        'batch_id': batch.id,
                        'account_id': account.id,
                        'base_nominal': base,
                        'coef_aplicado': coef_aplicado,
                        'monto_ajustado': monto_ajustado,
                        'delta_ajuste': delta,
                        'name': 'AJI %s | %s' % (batch.date_end, account.display_name),
                    })
                if results_to_create:
                    self.env['axi.result'].create(results_to_create)

                move_vals = {
                    'date': batch.date_end,
                    'journal_id': batch.journal_id.id,
                    'company_id': batch.company_id.id,
                    'ref': _('Ajuste por Inflación %s') % batch.name,
                    'line_ids': batch._build_move_lines(delta_by_account),
                }
                move = self.env['account.move'].create(move_vals)
                move.action_post()

                batch.write({
                    'move_id': move.id,
                    'state': 'posted',
                })
                move_to_open = move

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': move_to_open.id if move_to_open else False,
        }

    def action_reset_to_draft(self):
        for batch in self:
            if batch.move_id:
                if batch.move_id.state == 'posted':
                    batch.move_id.button_draft()
                # v15: requiere force_delete si el asiento estuvo posteado
                batch.move_id.with_context(force_delete=True).unlink()
            batch.result_ids.unlink()
            batch.state = 'draft'
        return True

    def action_view_results(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Resultados AXI'),
            'res_model': 'axi.result',
            'view_mode': 'tree,form',
            'domain': [('batch_id', '=', self.id)],
            'context': {'default_batch_id': self.id},
        }
