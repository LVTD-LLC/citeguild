---
name: property-based-testing
description: "Use when behavior has invariants, round trips, parsers, normalizers, state transitions, or broad input spaces that are better explored with Hypothesis than with enumerated examples alone."
---

# Property-Based Testing

Use Hypothesis to complement focused example-based tests. Start from a property
that must always hold, then design the smallest strategy that describes the
valid input space.

## Good Property Boundaries

- Round trips: serialize then deserialize, encode then decode, hash then verify.
- Invariants: normalization is idempotent, ordering is preserved, totals stay
  balanced, or permissions never broaden.
- Parsers and validators: valid inputs are accepted and malformed inputs fail
  safely without leaking data.
- State transitions: generated action sequences preserve domain constraints.
- Equivalent paths: two supported implementations or interfaces produce the
  same observable result.

Keep a small set of named examples for important business rules and regressions.
Property-based tests should explore the space around those examples, not make
the examples unreadable or disappear.

## Workflow

1. State the property in plain language before writing a strategy.
2. Put the test at the lowest useful boundary. Prefer pure functions and
   services when the database or request stack is not part of the property.
3. Start with built-in strategies from `hypothesis.strategies`. Compose
   domain-shaped strategies instead of generating arbitrary object graphs.
4. Use `@example(...)` for boundary cases that must always run.
5. Run the focused test and confirm a failure shrinks to a useful minimal
   counterexample before fixing the behavior.
6. Turn a discovered bug into a named regression example when it carries
   product meaning; Hypothesis will also replay cached failures locally.

```python
from hypothesis import example, given, strategies as st


@given(value=st.text(min_size=1))
@example(value="known-boundary")
def test_round_trip(value):
    assert decode(encode(value)) == value
```

Avoid `.example()` inside tests, broad `.filter()` calls, and excessive
`assume()` calls. They weaken generation and shrinking. Generate valid data by
construction instead.

## Django And Database Tests

Ordinary pure Hypothesis tests run under pytest without Django-specific setup.
When each generated example needs database access, inherit from
`hypothesis.extra.django.TestCase` or
`hypothesis.extra.django.TransactionTestCase`:

```python
from hypothesis import given, strategies as st
from hypothesis.extra.django import TestCase


class ProfilePropertyTests(TestCase):
    @given(first_name=st.text(max_size=30))
    def test_profile_name_round_trip(self, first_name):
        ...
```

Do not combine a plain `@given` database test with only
`@pytest.mark.django_db`; pytest-django does not provide the per-example
transaction handling Hypothesis requires. Keep database-backed properties
small, and use `hypothesis.extra.django.from_model()` only when model-generated
data is clearer than an explicit domain strategy.

## Running And Reproducing

Run property tests with the normal pytest targets:

```bash
make pytest-check -- apps/core/tests/test_api_keys.py -q
make terminal-test apps/core/tests/test_api_keys.py -q
```

Hypothesis prints reproduction details for failures. To replay a reported seed:

```bash
make pytest-check -- --hypothesis-seed=<seed> path/to/test_file.py -q
```

The generated `.gitignore` excludes `.hypothesis/`, which is a local replay
cache rather than a correctness dependency. Use `@example(...)` for inputs that
must always remain in the suite.

## Verification

- The property describes observable behavior, not implementation structure.
- Strategies generate representative valid and invalid boundaries without
  discarding most examples.
- The focused property test passes and remains fast enough for the normal
  pytest loop.
- Database access uses the Hypothesis Django test classes.
- Important fixed scenarios still have readable named tests or `@example`
  coverage.

## References

- https://hypothesis.readthedocs.io/en/latest/
- https://hypothesis.readthedocs.io/en/latest/quickstart.html
- https://hypothesis.readthedocs.io/en/latest/django.html
