import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from data_report_api import create_app
from data_report_api.config import TestConfig
from data_report_api.services import risk_monthly_analysis as module


class RiskMonthlyTests(unittest.TestCase):
    def setUp(self):
        self.source = MagicMock()
        self.source.database = 'sibebid'
        self.source.label = 'MySQL · sibebid'
        self.connection = self.source.connect.return_value
        self.cursor = self.connection.cursor.return_value
        self.cursor.fetchall.return_value = []
        self.source_patch = patch.object(module, 'DataSource', return_value=self.source)
        self.source_patch.start()
        self.log_patch = patch.object(module.logging.getLogger(module.__name__), 'exception')
        self.log_patch.start()
        self.addCleanup(self.source_patch.stop)
        self.addCleanup(self.log_patch.stop)

    def analyze(self, rows=(), **kwargs):
        self.cursor.fetchall.return_value = list(rows)
        return module.RiskMonthlyAnalysisService({'DATA_MODE': 'hive'}).analysis('2026-01-01', '2026-08-31', **kwargs)

    def test_ticket_sum_is_not_record_count_and_decimal_is_exact(self):
        result = self.analyze([('issue', '2026-01', 2, 5, Decimal('-102.0001'), 0, 0), ('refund', '2026-02', 1, 2, Decimal('0.0001'), 0, 0)])
        self.assertTrue(result['available'])
        self.assertEqual(result['businesses'][0]['metrics']['ticketCount'], 5)
        self.assertEqual(result['businesses'][0]['metrics']['rowCount'], 2)
        self.assertEqual(result['summary']['estimatedProfit'], '-102.0000')
        self.assertEqual(sum(Decimal(month['summary']['estimatedProfit']) for month in result['months'] if month['summary']['estimatedProfit'] is not None), Decimal(result['summary']['estimatedProfit']))

    def test_no_records_and_empty_months_are_not_zero_profit(self):
        result = self.analyze()
        self.assertTrue(result['available'])
        self.assertEqual(len(result['months']), 8)
        self.assertIsNone(result['summary']['estimatedProfit'])
        self.assertEqual(result['summary']['status'], 'no_records')
        self.assertIsNone(result['months'][0]['metrics']['issue']['ticketCount'])

    def test_missing_profit_keeps_known_amount_but_not_full_total(self):
        result = self.analyze([('issue', '2026-01', 2, 2, Decimal('-10.1234'), 0, 1), ('issue', '2026-02', 1, 1, Decimal('2.0001'), 0, 0)])
        metric = result['businesses'][0]['metrics']
        self.assertEqual(metric['ticketCount'], 3)
        self.assertEqual(metric['knownProfit'], '-8.1233')
        self.assertIsNone(metric['estimatedProfit'])
        self.assertIsNone(result['summary']['estimatedProfit'])
        self.assertIsNone(result['months'][0]['metrics']['issue']['estimatedProfit'])

    def test_all_missing_profit_and_ticket_totals_stay_null(self):
        result = self.analyze([('issue', '2026-01', 2, None, None, 2, 2)])
        metric = result['businesses'][0]['metrics']
        self.assertIsNone(metric['knownProfit'])
        self.assertIsNone(metric['knownTicketCount'])
        self.assertIsNone(metric['estimatedProfit'])
        self.assertIsNone(metric['ticketCount'])

    def test_missing_tickets_do_not_invalidate_known_profit(self):
        result = self.analyze([('issue', '2026-01', 2, 1, Decimal('-5.0000'), 1, 0)])
        self.assertIsNone(result['summary']['ticketCount'])
        self.assertEqual(result['summary']['estimatedProfit'], '-5.0000')

    def test_sql_is_a_single_union_and_only_three_reconciliation_sources(self):
        self.analyze()
        sql, parameters = self.cursor.execute.call_args.args
        self.assertEqual(sql.count('UNION ALL'), 2)
        self.assertEqual(parameters, ('2026-01-01', '2026-09-01') * 3)
        self.assertIn('SUM(ticket_num)', sql)
        self.assertIn('SUM(estimated_profit_cny)', sql)
        self.assertNotIn('coalesce', sql.lower())
        self.assertNotIn('JOIN', sql)
        self.assertNotIn('supplier_refund_operator', sql)
        self.assertNotIn('actual_profit_cny', sql)
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.cursor.close.assert_called_once()
        self.connection.close.assert_called_once()

    def test_source_date_matches_example_and_overview_date_remains_available(self):
        result = self.analyze()
        self.assertEqual(next(b for b in result['businesses'] if b['key'] == 'refund')['timeField'], 'stat_date')
        self.assertEqual(result['filters']['dateBasis'], 'reconcile')
        result = self.analyze(date_basis='overview')
        self.assertEqual(next(b for b in result['businesses'] if b['key'] == 'refund')['timeField'], 'business_date')

    def test_business_selection_only_queries_selected_table(self):
        result = self.analyze(business_type='refund')
        self.assertEqual(len(result['businesses']), 1)
        sql, parameters = self.cursor.execute.call_args.args
        self.assertIn('sibebid.bi_order_refund_profit_reconcile_year', sql)
        self.assertNotIn('bi_order_issue_profit_reconcile_year', sql)
        self.assertEqual(len(parameters), 2)

    def test_profit_conditions_are_source_record_level(self):
        for status, condition in [('loss', '< 0'), ('profit', '> 0'), ('zero', '= 0')]:
            self.analyze(profit_status=status)
            sql = self.cursor.execute.call_args.args[0]
            self.assertIn('AND estimated_profit_cny ' + condition, sql)
            self.assertNotIn('HAVING', sql)

    def test_invalid_inputs_rejected_before_connection(self):
        service = module.RiskMonthlyAnalysisService({})
        for kwargs in [{'business_type': "issue' OR 1=1"}, {'profit_status': 'invalid'}, {'date_basis': 'dt'}]:
            with self.assertRaises(ValueError): service.analysis(**kwargs)
        for first, last in [('invalid', '2026-09-18'), ('2026-09-19', '2026-09-18'), ('2025-01-01', '2026-09-18')]:
            with self.assertRaises(ValueError): service.analysis(first, last)
        self.source.connect.assert_not_called()

    def test_failure_clears_outputs_and_does_not_fallback_hive(self):
        self.cursor.execute.side_effect = Exception('private diagnostic')
        result = self.analyze()
        self.assertFalse(result['available'])
        self.assertNotIn('private', result['error'])
        self.assertEqual(result['months'], [])
        self.assertIsNone(result['summary']['estimatedProfit'])
        self.assertEqual(self.source.connect.call_count, 1)

    def test_source_override_does_not_change_other_modules(self):
        config = {'DATA_MODE': 'hive'}
        module.RiskMonthlyAnalysisService(config)
        self.assertEqual(config['DATA_MODE'], 'hive')
        self.assertEqual(module.DataSource.call_args.args[0]['DATA_MODE'], 'mysql')

    def test_month_bounds_partial_and_cross_year_labels(self):
        periods = module.month_periods(date(2025, 12, 20), date(2026, 2, 2))
        self.assertEqual([p['month'] for p in periods], ['2025-12', '2026-01', '2026-02'])
        self.assertEqual([p['isPartial'] for p in periods], [True, False, True])
        leap = module.month_periods(date(2024, 2, 1), date(2024, 2, 29))
        self.assertFalse(leap[0]['isPartial'])

    def test_date_or_count_inconsistency_not_published(self):
        for row in [('issue', 'bad-date', 1, 1, Decimal(1), 0, 0), ('issue', '2026-01', 1, 1, Decimal(1), 0, 2)]:
            self.assertFalse(self.analyze([row])['available'])

    def test_real_zero_profit_is_not_missing(self):
        result = self.analyze([('issue', '2026-01', 1, 1, Decimal('0.0000'), 0, 0)])
        self.assertEqual(result['summary']['estimatedProfit'], '0.0000')
        self.assertEqual(result['summary']['status'], 'ready')

    def test_route_input_validation(self):
        client = create_app(TestConfig).test_client()
        response = client.get('/api/v1/analysis/risk-monthly?startDate=2026-01-01&endDate=2026-08-31')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['data']['available'])
        self.assertEqual(client.get('/api/v1/analysis/risk-monthly?dateBasis=dt').status_code, 400)
        self.assertEqual(client.get('/api/v1/analysis/risk-monthly?businessType=invalid').status_code, 400)


if __name__ == '__main__':
    unittest.main()
