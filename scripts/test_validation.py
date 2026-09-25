"""Regression checks for accidental dataset corruption, not agent evaluation."""
import copy
import json
import unittest
from validate_dataset import ROOT, validate_record


class ValidationTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'data/initial_states/electrical/ph-bfar5bac-2024-007.json'
        self.record = json.loads(path.read_text(encoding='utf-8'))

    def reject(self, change):
        record = copy.deepcopy(self.record)
        change(record)
        with self.assertRaises((ValueError, KeyError)):
            validate_record(record)

    def test_valid_record(self):
        validate_record(self.record)

    def test_unresolved_document(self):
        self.reject(lambda r: r['source_provenance'][0].update(document_id='absent'))

    def test_unexplained_null(self):
        self.reject(lambda r: r.update(missing_information=[]))

    def test_unsupported_facts(self):
        self.reject(lambda r: r['source_provenance'].pop(0))

    def test_bad_pointer(self):
        self.reject(lambda r: r['source_provenance'][0].update(field_paths=['/not_a_field']))

    def test_wrong_estimate(self):
        self.reject(lambda r: r['line_items'][0]['estimated_total_cost'].update(amount=1))

    def test_mixed_currency(self):
        self.reject(lambda r: r['line_items'][0]['estimated_total_cost'].update(currency='USD'))

    def test_outcome_field_rejected(self):
        from jsonschema import ValidationError
        self.record['awarded_supplier'] = 'Outcome must not be in initial state'
        with self.assertRaises(ValidationError):
            validate_record(self.record)

    def test_invalid_date_rejected(self):
        from jsonschema import ValidationError
        self.record['schedule']['need_by_date'] = '2024-02-30'
        with self.assertRaises(ValidationError):
            validate_record(self.record)


if __name__ == '__main__':
    unittest.main()
