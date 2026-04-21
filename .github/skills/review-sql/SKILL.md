---
name: review-sql
description: Analyse and reformat T-SQL correction scripts for the CIR housing registration system. Use this when asked to analyse, review, or fix the formatting of a CIRHD SQL script.
---

# SQL Script Analysis & Formatting

When reviewing a SQL script, always do **both** steps in order:
1. **Reformat** the SQL file in place using the formatting rules below
2. **Analyse** the reformatted script and save findings to `<ticket>-analysis.md` in the same directory

When asked only to fix formatting, skip the analysis step.

## Formatting scope

**Formatting only** (apply automatically, no confirmation needed):
- Keyword casing, indentation, vertical alignment, semicolons, blank lines between sections
- Remove unnecessary square brackets

**Everything else** (ask the user before applying):
- Extracting hardcoded literals (IDs, dates, counts) into named `DECLARE` variables
- Adding a `BEGIN TRAN` / `@@ROWCOUNT` / `COMMIT TRAN` block where none exists
- Splitting one batch into multiple separate transactions
- Adding `RAISERROR` + `RETURN` to an existing rollback path
- Wrapping `SET IDENTITY_INSERT` inside a transaction
- Adding `AND REGI_RGST_CDE NOT IN ('RJCT', 'RFSD', 'ARCH')` to an existing `WHERE` clause
- Any other change that alters the **logic, structure, or values** of the script

When any of the above is needed, present the proposed change to the user and ask for confirmation before writing it to the file.

## Formatting

- All SQL keywords uppercase (`SELECT`, `FROM`, `WHERE`, `JOIN`, `UPDATE`, `SET`, `AND`, `BEGIN`, `END`, `COMMIT`, `ROLLBACK`, etc.)
- 4-space indentation inside `BEGIN TRAN`
- Align `SET` columns and `WHERE`/`AND` conditions vertically
- Each `AND` in a `JOIN … ON` block on its own line, indented to align with the first condition
- Subqueries indented one level deeper than the parent
- One blank line between logical sections
- Semicolons at the end of each DML statement
- No unnecessary square brackets around table or column names
- Extract magic numbers into named `DECLARE` variables with a comment (e.g. `DECLARE @RegiBaseId BIGINT = 51000000; -- Starting index of the Registration table`)

## Analysis

Save the analysis as `<ticket>-analysis.md` in the **same directory** as the SQL file.

### Structure

```
# <TICKET> — Script Analysis & Risks

## What the script does
<plain-language explanation, step by step for multi-step series>

## Risks

### 🔴 HIGH — <title>
<explanation + recommendation>

### 🟡 MEDIUM — <title>
<explanation>

### 🟢 LOW — <title>
<explanation>

## Execution order summary (for multi-step series)
| Step | File | Action | Max row guard |

## Risk summary
| Severity | Risk |
```

### What to flag as 🔴 HIGH

- No `BEGIN TRAN` / `@@ROWCOUNT` guard
- `RAISERROR` on rollback without `RETURN` — execution continues and `COMMIT TRAN` fires against a closed transaction
- `@@ROWCOUNT >= limit` instead of `> limit` — rolls back valid runs at the exact threshold
- `PRINT` instead of `RAISERROR` on rollback — silent in automated contexts
- `DECLARE` statements placed after the first `@@ROWCOUNT` check — if rollback fires, subsequent DML runs outside any transaction
- Unbounded DML with no row-count safety limit

### What to flag as 🟡 MEDIUM

- Fragile row-number alignment assumptions (e.g. `ROW_NUMBER() + 1` offset that breaks if row counts differ)
- Unbounded scope — query affects all matching rows in the DB, not scoped to ticket-specific IDs
- Batched updates (`UPDATE TOP (N)`) with no progress indicator or stop condition
- Complex `WHERE` logic duplicated across steps that must stay in sync
- Name-based lookups (`WHERE Name = '...'`) sensitive to duplicates
- Logic that silently skips rows due to multi-value preferences (e.g. registration has multiple city preferences — if WM still active in one, it won't be marked for deletion)
- Joins that may miss intended rows (e.g. joining on both `REGI_ID` and `PART_ID` when only `REGI_ID` was intended)
- Missing audit trail — no insert into `support.RegistrationActionComment` when `RegistrationAction` rows are inserted or updated
- Terminal statuses (`RJCT`, `RFSD`, `ARCH`) not excluded from DML scope

### What to flag as 🟢 LOW

- Implicit type conversions (e.g. numeric column compared to string `'99999'`)
- Copy-pasted code blocks (e.g. DST calculation repeated across multiple files)
- `DROP TABLE IF EXISTS` inside a `BEGIN TRAN` boundary

### What NOT to flag

- The absence of preview SELECTs — scripts are run by a team that does not act on query results

## Standard patterns to enforce

### Transaction with row-count guard

```sql
BEGIN TRAN
    DECLARE @maxUpdateCount INT = /* expected max */;

    -- ... DML ...

    IF @@ROWCOUNT > @maxUpdateCount
    BEGIN
        ROLLBACK TRAN;
        RAISERROR('Updated more rows than expected, reverting', 18, 1);
        RETURN;
    END

COMMIT TRAN;
```

### RegistrationAction insert

```sql
INSERT INTO RegistrationAction
    (REAC_REGI_ID, REAC_ACTP_CDE, REAC_RAST_CDE, REAC_USR_CRE, REAC_USR_CRE_DTE,
     REAC_RRN_NBR, REAC_RAST_IX, REAC_ASAS_CDE, REAC_Priority)
VALUES
    (<REGI_ID>, '<ACTP>', 'REQ', 'UHLPD', GETDATE(), '<RRN>', 1, 'AU', 900);
```

Always follow with an insert into `support.RegistrationActionComment` referencing the ticket number.

### Temp tables

```sql
IF OBJECT_ID('tempdb..#TableName') IS NOT NULL DROP TABLE #TableName;
-- ... use #TableName ...
DROP TABLE #TableName;
```

### Deleting a registration

```sql
EXEC sp_DeleteRegistration '<REF_NBR>';
```

### Excluding terminal statuses

```sql
WHERE REGI_RGST_CDE NOT IN ('RJCT', 'RFSD', 'ARCH')
```
