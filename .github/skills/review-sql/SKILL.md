---
name: create-script
description: Generate a new blank T-SQL correction script for a CIRHD ticket. Use this when asked to create a new script or scaffold a new ticket.
---

# New Script Generator

When asked to create a new script for a ticket:

1. Ask the user whether it is a **single-step** or **multi-step** script (if not already specified)
2. Ask for the **ticket number** (e.g. `CIRHD-12345`) if not already provided
3. Generate the file(s) in the current working directory using the templates below
4. For multi-step, ask how many steps are needed — accept any number (freeform input, not a fixed list) — and generate each file (`_1.sql`, `_2.sql`, …)

---

## Single-step template — `CIRHD-XXXXX.sql`

```sql
-- CIRHD-XXXXX
-- <Short description of what this script does>

DECLARE @maxUpdateCount INT = /* ??? */;

BEGIN TRAN

    -- TODO: DML here

    IF @@ROWCOUNT > @maxUpdateCount
    BEGIN
        ROLLBACK TRAN;
        RAISERROR('Updated more rows than expected, reverting', 18, 1);
        RETURN;
    END

COMMIT TRAN;
```

---

## Multi-step template

Each step gets its own file. Use this structure per step:

### `CIRHD-XXXXX_N.sql`

```sql
-- CIRHD-XXXXX — Step N: <Short description of this step>

DECLARE @maxUpdateCount INT = /* ??? */;

BEGIN TRAN

    -- TODO: DML here

    IF @@ROWCOUNT > @maxUpdateCount
    BEGIN
        ROLLBACK TRAN;
        RAISERROR('Updated more rows than expected, reverting', 18, 1);
        RETURN;
    END

COMMIT TRAN;
```

---

## Rules for generated scripts

- All `DECLARE` statements must be **above** `BEGIN TRAN`
- Use `@@ROWCOUNT > @maxUpdateCount` (not `>=`)
- Always `RAISERROR` (not `PRINT`) on rollback, followed immediately by `RETURN;`
- Use `'UHLPD'` for all `USR_CRE` / `USR_UPD` fields
- Exclude terminal statuses unless the ticket specifically targets them:
  ```sql
  AND REGI_RGST_CDE NOT IN ('RJCT', 'RFSD', 'ARCH')
  ```
- When inserting into `RegistrationAction`, always follow with an insert into `support.RegistrationActionComment`:
  ```sql
  INSERT INTO support.RegistrationActionComment (RegistrationActionId, CreatedOn, Comment)
  SELECT RegistrationActionId, GETDATE(), 'CIRHD-XXXXX <description>'
  FROM   #reacid;
  ```
- Check temp tables for existence before creating, and drop at end:
  ```sql
  IF OBJECT_ID('tempdb..#TableName') IS NOT NULL DROP TABLE #TableName;
  -- ...
  DROP TABLE #TableName;
  ```
- Extract magic numbers into named `DECLARE` variables with a comment

---

## Specialised file suffixes

If the ticket requires supporting files, generate them with the correct suffix:

| Suffix | Purpose |
|--------|---------|
| `_CREATE_ACTIONS.sql` | Inserts `RegistrationAction` rows to trigger processing |
| `_CLS_ACTIONS.sql` | Closes / clears action rows after processing |
| `_ACTION_PROGRESS.sql` | Monitoring query — no DML, no transaction needed |
| `_DAILY_REPORT.sql` | Recurring report — no DML, no transaction needed |
