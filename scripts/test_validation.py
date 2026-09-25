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

    def test_malformed_source_url_rejected(self):
        from jsonschema import ValidationError
        for url in ['not a URL', 'https://example.com/a b', 'https://[broken']:
            with self.subTest(url=url):
                record = copy.deepcopy(self.record)
                record['supporting_documents'][0]['url'] = url
                with self.assertRaises(ValidationError):
                    validate_record(record)

    def test_absence_reasons_require_null(self):
        for reason in ['not_stated', 'bidder_to_provide']:
            with self.subTest(reason=reason):
                self.reject(lambda r: r['missing_information'].append(dict(
                    field_path='/line_items/0/quantity', reason=reason,
                    detail='Must not claim a populated quantity is absent.')))

    def test_qualifying_notes_allow_populated_fields(self):
        for reason in ['conflicting_source', 'partial_extraction', 'retrospective_source']:
            with self.subTest(reason=reason):
                record = copy.deepcopy(self.record)
                record['missing_information'].append(dict(
                    field_path='/line_items', reason=reason, detail='Known limitation.'))
                validate_record(record)

    def test_composite_evidence_rejected(self):
        self.reject(lambda r: r['source_provenance'].append(dict(
            field_paths=['/line_items'], document_id='source-1',
            locator='Entire schedule', interpretation='Too broad to audit.')))

    def test_all_examples_have_scalar_evidence_paths(self):
        from validate_dataset import pointer
        for path in (ROOT / 'data/initial_states/electrical').glob('*.json'):
            record = json.loads(path.read_text(encoding='utf-8'))
            for evidence in record['source_provenance']:
                for field in evidence['field_paths']:
                    with self.subTest(package=path.name, field=field):
                        self.assertNotIsInstance(pointer(record, field), (dict, list))

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
