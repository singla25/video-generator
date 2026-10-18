"""Batch creation: sheet upload, mapping, validation report, limits (AC2, AC3, AC4, D-8, D-18)."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME
from tests.integration.api.batch_helpers import (
    create_batch,
    csv_bytes,
    get_batch,
    new_batch,
    people,
    row_ids,
    row_status,
    table_count,
    usable_template,
    xlsx_bytes,
)
from tests.integration.api.conftest import Env, EnvFactory
from tests.integration.api.helpers import new_template
from vidgen.domain.codes import FailureCode, plain_message
from vidgen.infrastructure.db.models import Batch, BatchRow

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
DEVANAGARI = "\u0930\u093e\u091c\u0947\u0936 \u0915\u0941\u092e\u093e\u0930"


# ---- positive -------------------------------------------------------------------------


def test_csv_upload_creates_a_draft_batch_with_a_validation_report(env: Env) -> None:
    """TT-AC2-P2, AC3-P6: counts and an empty problem list for a clean sheet."""
    template_id = usable_template(env)
    response = create_batch(env, template_id, people(5))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["template_id"] == template_id
    assert body["preview"] == {"status": "NONE", "approved": False}
    assert body["report"] == {"total_rows": 5, "valid_rows": 5, "skipped_rows": 0, "problems": []}


def test_xlsx_upload_works_and_reports_the_first_sheet_name(env: Env) -> None:
    """TT-AC2-P1, E7 (B9)."""
    content = xlsx_bytes(
        {"Voters": [["Name", "ID"], *people(2)], "Other": [["Name", "ID"], ["Zed", "Z9"]]}
    )
    template_id = usable_template(env)
    response = create_batch(env, template_id, content=content, filename="s.xlsx")
    assert response.status_code == 201
    assert response.json()["sheet_name"] == "Voters"
    assert response.json()["report"]["total_rows"] == 2


def test_headers_match_case_insensitively_with_spaces_trimmed(env: Env) -> None:
    """TT-AC2-P3: ' VID ' matches 'vid'."""
    template_id = usable_template(env)
    response = create_batch(
        env,
        template_id,
        people(2),
        header=["NAME ", " vid "],
        name_column="name",
        id_column="VID",
    )
    assert response.status_code == 201


def test_spoken_name_column_is_optional_and_accepted(env: Env) -> None:
    """TT-AC2-P4, P5."""
    template_id = usable_template(env)
    rows = [["Asha", "A1", "Aasha"], ["Bina", "B2", ""]]
    response = create_batch(
        env,
        template_id,
        rows,
        header=["Name", "ID", "Spoken name"],
        spoken_column="spoken name",
    )
    assert response.status_code == 201
    listing = env.client.get(f"/batches/{response.json()['id']}/rows").json()["rows"]
    assert [r["spoken_name"] for r in listing] == ["Aasha", None]


def test_extra_columns_are_ignored(env: Env) -> None:
    """TT-AC2-P6."""
    template_id = usable_template(env)
    response = create_batch(
        env, template_id, [["Asha", "A1", "555-0100"]], header=["Name", "ID", "Phone"]
    )
    assert response.status_code == 201
    assert "555-0100" not in env.client.get(f"/batches/{response.json()['id']}/rows").text


@pytest.mark.parametrize("delimiter", [";", "\t"])
def test_semicolon_and_tab_delimited_csv_is_sniffed(env: Env, delimiter: str) -> None:
    """TT-AC2-E11 (B9)."""
    content = csv_bytes([["Name", "ID"], *people(2)], delimiter=delimiter)
    response = create_batch(env, usable_template(env), content=content)
    assert response.status_code == 201
    assert response.json()["report"]["valid_rows"] == 2


def test_bom_csv_and_devanagari_names_are_read_correctly(env: Env) -> None:
    """TT-AC2-E1, AC3-P2."""
    content = csv_bytes([["Name", "ID"], [DEVANAGARI, "D1"]], bom=True)
    batch_id = create_batch(env, usable_template(env), content=content).json()["id"]
    row = env.client.get(f"/batches/{batch_id}/rows").json()["rows"][0]
    assert row["name"] == DEVANAGARI


def test_blank_rows_are_skipped_and_row_numbers_stay_true(env: Env) -> None:
    """TT-AC2-E4: row numbers in the report are sheet rows."""
    rows = [["Asha", "A1"], ["", ""], ["", "B2"], ["Chand", "C3"]]
    template_id = usable_template(env)
    body = create_batch(env, template_id, rows).json()
    assert body["report"]["total_rows"] == 3
    assert [p["row_number"] for p in body["report"]["problems"]] == [4]


def test_one_row_sheet_makes_a_batch_of_one(env: Env) -> None:
    """TT-AC2-E5."""
    body = create_batch(env, usable_template(env), people(1)).json()
    assert body["report"]["total_rows"] == 1


def test_batch_can_be_read_back_and_listed(env: Env) -> None:
    """TT-AC14-P5."""
    batch_id = new_batch(env)
    assert get_batch(env, batch_id)["id"] == batch_id
    listed = env.client.get("/batches").json()["batches"]
    assert [b["id"] for b in listed] == [batch_id]


def test_report_endpoint_returns_the_same_report(env: Env) -> None:
    """TT-AC3-P6."""
    batch_id = new_batch(env, [["Asha", "A1"], ["", "B2"]])
    report = env.client.get(f"/batches/{batch_id}/report").json()
    assert (report["total_rows"], report["valid_rows"], report["skipped_rows"]) == (2, 1, 1)


# ---- validation report ----------------------------------------------------------------


def test_every_invalid_row_gets_its_code_and_plain_message(env: Env, db: Engine) -> None:
    """TT-AC3-N1..N5, AC3-N3: invalid rows are SKIPPED with R8 codes."""
    rows = [
        ["Asha", "A1"],  # row 2 ok
        ["", "B2"],  # row 3 empty name
        ["Chand", ""],  # row 4 empty id
        ["Asha Again", "A1"],  # row 5 duplicate of row 2
        ["A" * 41, "E5"],  # row 6 too long
        ["Raj3sh", "F6"],  # row 7 bad characters
    ]
    body = create_batch(env, usable_template(env), rows).json()
    problems = {p["row_number"]: p for p in body["report"]["problems"]}
    assert body["report"]["skipped_rows"] == 5
    assert problems[3]["code"] == "INVALID_ROW_EMPTY_NAME"
    assert problems[4]["code"] == "INVALID_ROW_EMPTY_ID"
    assert problems[5]["code"] == "DUPLICATE_ID"
    assert problems[5]["message"] == plain_message(FailureCode.DUPLICATE_ID, row=2)
    assert problems[6]["code"] == "INVALID_ROW_NAME_TOO_LONG"
    assert problems[7]["code"] == "INVALID_ROW_BAD_CHARACTERS"
    assert row_status(db, body["id"]) == {
        2: "QUEUED",
        3: "SKIPPED",
        4: "SKIPPED",
        5: "SKIPPED",
        6: "SKIPPED",
        7: "SKIPPED",
    }


def test_multi_fault_row_lists_every_fault_with_the_primary_first(env: Env) -> None:
    """TT-AC3-N6, E13 (B1)."""
    body = create_batch(env, usable_template(env), [["@" * 41, ""]]).json()
    problem = body["report"]["problems"][0]
    assert problem["code"] == "INVALID_ROW_EMPTY_ID"
    assert problem["faults"] == [
        "INVALID_ROW_EMPTY_ID",
        "INVALID_ROW_BAD_CHARACTERS",
        "INVALID_ROW_NAME_TOO_LONG",
    ]


def test_graphemes_not_code_points_decide_the_length_limit(env: Env) -> None:
    """TT-AC3-E2 (A1): 40 Devanagari graphemes (80 code points) are fine, 41 are not."""
    ka_i = "\u0915\u093f"
    body = create_batch(env, usable_template(env), [[ka_i * 40, "A1"], [ka_i * 41, "A2"]]).json()
    assert [p["row_number"] for p in body["report"]["problems"]] == [3]


@pytest.mark.parametrize(
    ("first", "second"), [("RJ/12/097", "rj_12_097"), ("A/1", "A_1"), ("STRASSE", "Stra\u00dfe")]
)
def test_ids_that_would_share_a_file_name_are_duplicates_and_never_a_500(
    env: Env, db: Engine, first: str, second: str
) -> None:
    """TT-AC3-E5, D-18: the later row is SKIPPED as DUPLICATE_ID; no server error."""
    response = create_batch(env, usable_template(env), [["Asha", first], ["Bina", second]])
    assert response.status_code == 201
    assert [p["code"] for p in response.json()["report"]["problems"]] == ["DUPLICATE_ID"]
    assert row_status(db, response.json()["id"]) == {2: "QUEUED", 3: "SKIPPED"}


def test_a_second_sheet_with_the_same_ids_in_another_batch_is_fine(env: Env) -> None:
    """TT-AC3-E9: the duplicate rule is per batch."""
    template_id = usable_template(env)
    assert create_batch(env, template_id, people(2)).status_code == 201
    assert create_batch(env, template_id, people(2)).status_code == 201


def test_all_rows_invalid_still_creates_the_batch_with_a_full_report(env: Env) -> None:
    """TT-AC3-E11: the report is produced; nothing can be previewed or started."""
    body = create_batch(env, usable_template(env), [["", "A1"], ["", "B2"]]).json()
    assert body["report"]["valid_rows"] == 0
    assert env.client.post(f"/batches/{body['id']}/preview", headers=env.csrf).status_code == 409


def test_rows_are_stored_encrypted_and_readable_for_the_admin(env: Env, db: Engine) -> None:
    """TT-AC17-P2, B6: the raw table holds no plaintext, the API returns it."""
    from sqlalchemy import text

    batch_id = new_batch(env, [[CANARY_NAME.replace("-", " "), CANARY_ID], ["Asha", "A2"]])
    with db.connect() as conn:
        raw = "\n".join(conn.execute(text("SELECT t::text FROM batch_rows t")).scalars())
    assert "Canary" not in raw
    assert "CANARY1" not in raw
    rows = env.client.get(f"/batches/{batch_id}/rows").json()["rows"]
    assert rows[0]["voter_id"] == CANARY_ID


# ---- negative: template gate, mapping, files ------------------------------------------


def test_template_without_consent_cannot_be_used(env: Env, db: Engine) -> None:
    """TT-AC5-N1: CONSENT_MISSING, no batch."""
    template_id = new_template(env)
    response = create_batch(env, template_id, people(2))
    assert response.status_code == 409
    assert response.json()["code"] == "CONSENT_MISSING"
    assert table_count(db, Batch) == 0


def test_template_with_unconfirmed_slot_cannot_be_used(env: Env, db: Engine) -> None:
    """TT-AC6-N6: SLOT_NOT_FOUND, no batch."""
    from tests.fixtures.doubles import pdf_bytes
    from tests.integration.api.helpers import upload_consent

    template_id = new_template(env)
    upload_consent(env, template_id, content=pdf_bytes())
    response = create_batch(env, template_id, people(2))
    assert response.status_code == 409
    assert response.json()["code"] == "SLOT_NOT_FOUND"
    assert table_count(db, Batch) == 0


def test_unknown_template_is_404(env: Env) -> None:
    """TT-AC2-N1."""
    response = create_batch(env, UNKNOWN_ID, people(2))
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize("missing", ["Name", "ID"])
def test_mapped_column_that_does_not_exist_gives_column_not_found_and_no_batch(
    env: Env, db: Engine, missing: str
) -> None:
    """TT-AC2-N1, N2."""
    kwargs = {"name_column": "Nope"} if missing == "Name" else {"id_column": "Nope"}
    response = create_batch(env, usable_template(env), people(2), **kwargs)
    assert response.status_code == 422
    assert response.json()["code"] == "COLUMN_NOT_FOUND"
    assert table_count(db, Batch) == 0
    assert table_count(db, BatchRow) == 0


def test_missing_spoken_name_column_is_column_not_found(env: Env, db: Engine) -> None:
    """TT-AC2-N1."""
    response = create_batch(env, usable_template(env), people(2), spoken_column="Spoken")
    assert response.json()["code"] == "COLUMN_NOT_FOUND"
    assert table_count(db, Batch) == 0


def test_name_and_id_mapped_to_the_same_column_is_refused(env: Env, db: Engine) -> None:
    """TT-AC2-N6 (D-7: COLUMN_NOT_FOUND)."""
    response = create_batch(env, usable_template(env), people(2), id_column="name")
    assert response.status_code == 422
    assert response.json()["code"] == "COLUMN_NOT_FOUND"
    assert table_count(db, Batch) == 0


def test_headers_that_collide_after_normalisation_are_refused(env: Env, db: Engine) -> None:
    """TT-AC2-N5 (D-7: UNSUPPORTED_SHEET)."""
    response = create_batch(
        env, usable_template(env), [["A", "1", "2"]], header=["Name", "ID", "id "]
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SHEET"
    assert table_count(db, Batch) == 0


@pytest.mark.parametrize("filename", ["s.xls", "s.txt", "s.ods", "s"])
def test_unsupported_sheet_types_are_refused_and_nothing_is_stored(
    env: Env, db: Engine, filename: str
) -> None:
    """TT-AC2-N3."""
    template_id = usable_template(env)
    stored_before = len(env.storage.files)
    response = create_batch(env, template_id, people(2), filename=filename)
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SHEET"
    assert len(env.storage.files) == stored_before
    assert table_count(db, Batch) == 0


def test_corrupt_xlsx_is_refused(env: Env, db: Engine) -> None:
    """TT-AC2-N4."""
    response = create_batch(
        env, usable_template(env), content=b"PK\x03\x04 not really", filename="s.xlsx"
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SHEET"
    assert table_count(db, Batch) == 0


def test_sheet_with_headers_only_is_refused(env: Env, db: Engine) -> None:
    """TT-AC2-E3."""
    response = create_batch(env, usable_template(env), content=csv_bytes([["Name", "ID"]]))
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SHEET"
    assert table_count(db, Batch) == 0


def test_empty_file_is_refused(env: Env) -> None:
    """TT-AC2-E3."""
    response = create_batch(env, usable_template(env), content=b"")
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SHEET"


def test_request_without_a_sheet_or_mapping_is_a_validation_error(env: Env) -> None:
    """TT-AC2-N1."""
    template_id = usable_template(env)
    no_file = env.client.post("/batches", data={"template_id": template_id}, headers=env.csrf)
    assert no_file.status_code == 422
    assert no_file.json()["code"] == "VALIDATION_ERROR"
    no_mapping = create_batch(env, template_id, people(2), name_column=None)
    assert no_mapping.status_code == 422
    assert no_mapping.json()["code"] == "VALIDATION_ERROR"


# ---- limits ---------------------------------------------------------------------------


def test_sheet_over_the_row_limit_is_refused_with_a_coded_error(
    make_env: EnvFactory, db: Engine
) -> None:
    """TT-AC4-N2 (D-8): the batch service enforces max_sheet_rows."""
    env = make_env(max_sheet_rows=5)
    template_id = usable_template(env)
    response = create_batch(env, template_id, people(6))
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SHEET"
    assert table_count(db, Batch) == 0


def test_sheet_exactly_at_the_row_limit_is_accepted(make_env: EnvFactory) -> None:
    """TT-AC4-N2 boundary."""
    env = make_env(max_sheet_rows=5)
    assert create_batch(env, usable_template(env), people(5)).status_code == 201


def test_oversize_sheet_is_413_and_not_stored(make_env: EnvFactory, db: Engine) -> None:
    """TT-AC4-N2: byte limit enforced while streaming."""
    env = make_env(max_sheet_bytes=2048)
    template_id = usable_template(env)
    stored_before = len(env.storage.files)
    response = create_batch(env, template_id, people(500))
    assert response.status_code == 413
    assert response.json()["code"] == "UNSUPPORTED_SHEET"
    assert len(env.storage.files) == stored_before
    assert table_count(db, Batch) == 0


def test_a_thousand_row_sheet_is_validated_quickly(env: Env) -> None:
    """TT-AC4-P1: the whole request, including database writes, stays under a few seconds."""
    import time

    template_id = usable_template(env)
    started = time.perf_counter()
    response = create_batch(env, template_id, people(1000))
    assert response.status_code == 201
    assert response.json()["report"]["valid_rows"] == 1000
    assert time.perf_counter() - started < 10


def test_row_ids_exist_for_every_row_including_skipped_ones(env: Env, db: Engine) -> None:
    """AC11-P6 groundwork: the manifest needs a line per input row."""
    batch_id = new_batch(env, [["Asha", "A1"], ["", "B2"]])
    assert sorted(row_ids(db, batch_id)) == [2, 3]


def test_hostile_sheet_file_names_are_not_stored_or_echoed(env: Env) -> None:
    """TT-AC2-E10."""
    response = create_batch(
        env, usable_template(env), people(2), filename=f"../../{CANARY_NAME}.csv"
    )
    assert response.status_code == 201
    assert CANARY_NAME not in response.text
    assert all(CANARY_NAME not in key and ".." not in key for key in env.storage.files)
