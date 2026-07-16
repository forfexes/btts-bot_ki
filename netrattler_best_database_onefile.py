Help me to debug the attached sql snippet which gives the following error:

Failed to run sql query: ERROR: 42703: column "source_id" does not exist LINE 24: where source_id is null or source_id = ''; ^ HINT: Perhaps you meant to reference the column "netrattler_source_registry.source".




Reasoned
What the error means
Postgres is telling you that, in the WHERE clause around line 24, your query references a column named source_id, but there is no column with that exact name visible in the scope of that query.

The hint:

Perhaps you meant netrattler_source_registry.source

suggests that the “source id” you intended to filter on is actually stored in a column named source (under the table netrattler_source_registry), not source_id.

So you likely have one of these issues:

The column name is wrong (source_id doesn’t exist; the real column is source)
You’re filtering in a subquery/CTE where source_id isn’t selected / isn’t in the FROM scope
You meant table_alias.source_id but forgot the alias (or the alias doesn’t match)
I can debug it precisely—paste the snippet
Please paste the SQL snippet (or at least):

lines 20–30 (where the error points),
the FROM / JOIN section that defines which tables/aliases are in play,
any CTEs (WITH ...) if the WHERE is inside one.
Quick self-check you can do immediately
Search your query for source_id
Check whether the table you’re querying has a column named source_id
If the hint is correct, change the filter to use the actual column, e.g.:
SQL Query



WHERE netrattler_source_registry.source IS NULL
   OR netrattler_source_registry.source = ''

(or if you’re using an alias, use the alias, e.g. nsr.source)

Next step
Paste the snippet and I’ll tell you exactly what to change (including the correct column/alias) and why.



Supabase AI may not always produce correct answers. Double check responses.

