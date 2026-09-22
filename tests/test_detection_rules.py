from adaptive_disclosure_gateway.detection import Detector


def _spans_by_category(text: str) -> dict[str, list]:
    spans = Detector().detect(text)
    by_category: dict[str, list] = {}
    for span in spans:
        by_category.setdefault(span.category, []).append(span)
    return by_category


def test_cpf_detected_with_correct_offsets():
    text = "Contact CPF: 123.456.789-09 today."
    by_category = _spans_by_category(text)

    assert len(by_category["cpf"]) == 1
    span = by_category["cpf"][0]
    assert span.value == "123.456.789-09"
    assert text[span.start : span.end] == span.value


def test_cnpj_detected_with_correct_offsets():
    text = "Vendor CNPJ 12.345.678/0001-95 on file."
    by_category = _spans_by_category(text)

    assert len(by_category["cnpj"]) == 1
    span = by_category["cnpj"][0]
    assert span.value == "12.345.678/0001-95"
    assert text[span.start : span.end] == span.value
    assert "cpf" not in by_category


def test_email_detected_with_correct_offsets():
    text = "reach me at ana.souza@example.com now"
    by_category = _spans_by_category(text)

    assert len(by_category["email"]) == 1
    span = by_category["email"][0]
    assert span.value == "ana.souza@example.com"
    assert text[span.start : span.end] == span.value


def test_phone_detected_with_correct_offsets():
    text = "call (11) 98765-4321 please"
    by_category = _spans_by_category(text)

    assert len(by_category["phone"]) == 1
    span = by_category["phone"][0]
    assert span.value == "(11) 98765-4321"
    assert text[span.start : span.end] == span.value


def test_unformatted_digit_run_is_not_treated_as_cpf():
    # Deliberate scope limit: only the canonical punctuated CPF format is
    # matched. An unformatted 11-digit run is not a CPF match, avoiding
    # collisions with phone numbers or other numeric identifiers.
    text = "reference number 12345678901 was issued"
    by_category = _spans_by_category(text)

    assert "cpf" not in by_category


def test_labeled_employee_name_excludes_label_prefix():
    text = "Employee: Ana Souza\nDepartment: Engineering\n"
    by_category = _spans_by_category(text)

    assert len(by_category["employee_name"]) == 1
    span = by_category["employee_name"][0]
    assert span.value == "Ana Souza"
    assert text[span.start : span.end] == "Ana Souza"


def test_labeled_salary_excludes_label_prefix():
    text = "Salary: R$ 8500.00\n"
    by_category = _spans_by_category(text)

    span = by_category["salary"][0]
    assert span.value == "R$ 8500.00"
    assert text[span.start : span.end] == span.value


def test_labeled_salary_keeps_lf_offsets_for_brazilian_amount():
    text = "Salary: R$ 8.500,00\n"
    by_category = _spans_by_category(text)

    span = by_category["salary"][0]
    assert span.category == "salary"
    assert span.value == "R$ 8.500,00"
    assert text[span.start : span.end] == span.value
    assert text[span.end : span.end + 1] == "\n"


def test_labeled_salary_excludes_crlf_line_ending_from_value():
    text = "Salary: R$ 8.500,00\r\n"
    by_category = _spans_by_category(text)

    span = by_category["salary"][0]
    assert span.category == "salary"
    assert span.value == "R$ 8.500,00"
    assert text[span.start : span.end] == span.value
    assert text[span.end : span.end + 2] == "\r\n"


def test_labeled_department_excludes_label_prefix():
    text = "Department: Engineering\n"
    by_category = _spans_by_category(text)

    span = by_category["department"][0]
    assert span.value == "Engineering"
    assert text[span.start : span.end] == span.value


def test_labeled_medical_data_captures_full_remainder_of_line():
    text = "Medical notes: Reports chronic migraine and requested leave.\n"
    by_category = _spans_by_category(text)

    span = by_category["medical_data"][0]
    assert span.value == "Reports chronic migraine and requested leave."
    assert text[span.start : span.end] == span.value


def test_labeled_contract_amounts_exclude_crlf_line_endings_from_values():
    text = "Contract value: R$ 125.000,00\r\nPenalty: R$ 12.500,00\r\n"
    by_category = _spans_by_category(text)

    contract_value = by_category["contract_value"][0]
    assert contract_value.category == "contract_value"
    assert contract_value.value == "R$ 125.000,00"
    assert text[contract_value.start : contract_value.end] == contract_value.value
    assert text[contract_value.end : contract_value.end + 2] == "\r\n"

    penalty = by_category["penalty_amount"][0]
    assert penalty.category == "penalty_amount"
    assert penalty.value == "R$ 12.500,00"
    assert text[penalty.start : penalty.end] == penalty.value
    assert text[penalty.end : penalty.end + 2] == "\r\n"


def test_labeled_contract_amounts_keep_lf_offsets_unchanged():
    text = "Contract value: R$ 125.000,00\nPenalty: R$ 12.500,00\n"
    by_category = _spans_by_category(text)

    contract_value = by_category["contract_value"][0]
    assert contract_value.value == "R$ 125.000,00"
    assert text[contract_value.start : contract_value.end] == contract_value.value

    penalty = by_category["penalty_amount"][0]
    assert penalty.value == "R$ 12.500,00"
    assert text[penalty.start : penalty.end] == penalty.value


def test_detector_is_deterministic_across_runs():
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"

    first = Detector().detect(text)
    second = Detector().detect(text)

    assert [(s.category, s.value, s.start, s.end) for s in first] == [
        (s.category, s.value, s.start, s.end) for s in second
    ]
