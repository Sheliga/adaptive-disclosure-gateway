"""DEVELOPMENT-ONLY synthetic Contracts fixtures (Issue #56).

**This file is development evidence. It is NOT corpus material and must not
be reused as held-out/confirmatory evidence without an explicit, recorded
methodological decision.** It lives under ``tests/`` and never under
``corpus/`` for exactly that reason: ``corpus/`` is the frozen, oracle-
bearing evaluation surface (T24 / Issue #37 owns the Contracts v1 corpus),
while everything here exists only to make a behaviour observable while it is
being built.

Every party, representative, identifier, amount, account and date below is
invented for this test suite. No employer, client, counterparty or otherwise
confidential document contributed a single value.

Deliberately named without a ``test_`` prefix so pytest never collects it on
its own -- it is imported by ``tests/test_contracts_domain.py``.

Shape of the fixtures, and why it is shaped this way
----------------------------------------------------

The detector is a labeled-line matcher, not a named-entity recognizer (see
``detection/rules.py``). For the Contracts domain that has one consequence
worth stating up front, because it is what makes party *roles* survive
pseudonymization at all:

    the ROLE lives in the label; the IDENTITY lives in the value.

``Contracting party: Aurora ...`` detects only ``Aurora ...`` (the rule
captures its ``value`` group), so the role word ``Contracting party`` is
never inside a detected span and is therefore never removed, banded or
pseudonymized. The payload keeps ``Contracting party: PSEUDO-party_name-...``
-- who is who is hidden, which role is which is not. That is the whole
"preserve party roles / preserve obligation assignment" requirement, and it
needs no relation model: see
``tests/test_contracts_domain.py``'s relation-preservation tests.

The amendment block repeats both parties on purpose: the vault issues a
*stable* pseudonym per original value within a scope, so the same party must
resolve to the same pseudonym in both blocks. That stability is what carries
"the same company owes this obligation in both documents" across the
disclosure boundary.
"""

from __future__ import annotations

# The main relation fixture. No ``Bank account:`` line -- that category
# blocks the whole request by design, so it gets its own fixture below.
CONTRACTS_FIXTURE = (
    "CONTRACT\n"
    "Contracting party: Aurora Servicos Digitais Ltda\n"
    "CNPJ: 12.345.678/0001-90\n"
    "Contracted party: Boreal Engenharia SA\n"
    "CNPJ: 98.765.432/0001-10\n"
    "Representative: Marina Alves Pereira\n"
    "CPF: 123.456.789-09\n"
    "Contract value: R$ 2400000.00\n"
    "Penalty: R$ 12000.00\n"
    "Deadline: 2026-03-31\n"
    "\n"
    "AMENDMENT 1\n"
    "Contracting party: Aurora Servicos Digitais Ltda\n"
    "Contracted party: Boreal Engenharia SA\n"
    "Deadline: 2026-09-30\n"
)

CONTRACTING_PARTY = "Aurora Servicos Digitais Ltda"
CONTRACTED_PARTY = "Boreal Engenharia SA"
REPRESENTATIVE = "Marina Alves Pereira"
CONTRACTING_PARTY_CNPJ = "12.345.678/0001-90"
CONTRACTED_PARTY_CNPJ = "98.765.432/0001-10"
REPRESENTATIVE_CPF = "123.456.789-09"
CONTRACT_VALUE = "R$ 2400000.00"
PENALTY_AMOUNT = "R$ 12000.00"
FIRST_DEADLINE = "2026-03-31"
AMENDED_DEADLINE = "2026-09-30"

#: Every sensitive original value in ``CONTRACTS_FIXTURE``, for leak scans.
CONTRACTS_FIXTURE_SENSITIVE_VALUES = (
    CONTRACTING_PARTY,
    CONTRACTED_PARTY,
    REPRESENTATIVE,
    CONTRACTING_PARTY_CNPJ,
    CONTRACTED_PARTY_CNPJ,
    REPRESENTATIVE_CPF,
    CONTRACT_VALUE,
    PENALTY_AMOUNT,
    FIRST_DEADLINE,
    AMENDED_DEADLINE,
)

# A bank account is BLOCK_REQUEST in every treatment and in `contracts-v1`,
# so a fixture containing one can only ever be used to pin that block.
CONTRACTS_BANK_ACCOUNT_FIXTURE = (
    "Contracting party: Aurora Servicos Digitais Ltda\n"
    "Bank account: 001 / 1234 / 56789-0\n"
    "Contract value: R$ 2400000.00\n"
)

BANK_ACCOUNT = "001 / 1234 / 56789-0"

# A party named once on its own labeled line and once inside ordinary
# contract prose. The prose mention is NOT detected -- see
# ``tests/test_contracts_domain.py``'s documented-limitation test and
# `docs/contracts-policy-matrix.md`'s "Known limitations" section. This
# fixture exists to keep that gap visible and measured, not to suggest it is
# handled.
CONTRACTS_COREFERENCE_FIXTURE = (
    "Contracting party: Aurora Servicos Digitais Ltda\n"
    "Contracted party: Boreal Engenharia SA\n"
    "Clause 4: Aurora Servicos Digitais Ltda shall pay the contract value "
    "to Boreal Engenharia SA on the deadline.\n"
)
