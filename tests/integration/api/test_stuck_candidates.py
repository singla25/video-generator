"""L10(d): the SQL query behind requeue_stuck_rows (BatchStore.stuck_candidates).

Only QUEUED rows of RUNNING batches started before the cutoff, plus pending previews of DRAFT
batches; RUNNING/DONE rows and fresh batches are never returned.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from tests.integration.api.batch_helpers import (
    new_batch,
    post_action,
    row_ids,
    running_batch,
    set_rows,
)
from tests.integration.api.conftest import Env
from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher
from vidgen.infrastructure.db.batch_store import SqlBatchStore


def store_for(env: Env, session: Session) -> SqlBatchStore:
    """A batch store with the app's cipher."""
    settings = env.settings
    cipher = AesGcmCipher(
        keys={settings.encryption_key_id: settings.encryption_key_bytes()},
        active_key_id=settings.encryption_key_id,
        index_key=settings.index_key_bytes(),
    )
    return SqlBatchStore(session, cipher)


def candidates(env: Env, db: Engine, **kw: object) -> list:
    """All candidates older than ``stuck_after`` seconds from the fake clock."""
    cutoff = env.clock.now() - timedelta(seconds=int(kw.get("older_than", 600)))  # type: ignore[call-overload]
    with Session(db) as session:
        return store_for(env, session).stuck_candidates(cutoff, None, 1000)


def test_queued_rows_of_an_old_running_batch_are_candidates(env: Env, db: Engine) -> None:
    batch_id = running_batch(env)
    env.advance(seconds=700)
    found = candidates(env, db)
    assert {c.row_id for c in found} == set(row_ids(db, batch_id).values())
    assert {c.kind for c in found} == {"row"}


def test_a_fresh_batch_is_not_touched(env: Env, db: Engine) -> None:
    running_batch(env)
    assert candidates(env, db) == []


def test_rows_already_running_or_done_are_not_candidates(env: Env, db: Engine) -> None:
    batch_id = running_batch(env)
    ids = row_ids(db, batch_id)
    numbers = sorted(ids)
    set_rows(db, batch_id, numbers[:1], status="PROCESSING")
    set_rows(db, batch_id, numbers[1:2], status="COMPLETED")
    set_rows(db, batch_id, numbers[2:3], status="FAILED")
    env.advance(seconds=700)
    found = {c.row_id for c in candidates(env, db)}
    assert found == {ids[n] for n in numbers[3:]}


def test_draft_batches_rows_are_not_candidates_but_a_pending_preview_is(
    env: Env, db: Engine
) -> None:
    batch_id = new_batch(env)
    assert post_action(env, batch_id, "preview").status_code == 202
    env.advance(seconds=700)
    found = candidates(env, db)
    assert [c.kind for c in found] == ["preview"]
    assert isinstance(found[0].row_id, UUID)


def test_paging_by_row_id_returns_every_row_exactly_once(env: Env, db: Engine) -> None:
    from tests.integration.api.batch_helpers import people

    batch_id = running_batch(env, people(7))
    env.advance(seconds=700)
    cutoff = env.clock.now() - timedelta(seconds=600)
    seen: list[UUID] = []
    after: UUID | None = None
    with Session(db) as session:
        store = store_for(env, session)
        while page := store.stuck_candidates(cutoff, after, 3):
            assert len(page) <= 3
            seen.extend(c.row_id for c in page)
            after = page[-1].row_id
    assert sorted(seen) == sorted(row_ids(db, batch_id).values())


def test_no_batches_gives_no_candidates(env: Env, db: Engine) -> None:
    assert candidates(env, db) == []
