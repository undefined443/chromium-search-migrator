# chromium-search-migrator

Migrate active Chromium search engines from one `Web Data` database into another.

This is useful for moving custom search engines from Arc Browser to Google Chrome.

## Usage

Dry run:

```sh
uv run chromium-search-migrator \
  "$HOME/Library/Application Support/Arc/User Data/Default/Web Data" \
  "$HOME/Library/Application Support/Google/Chrome/Default/Web Data"
```

Apply changes:

```sh
uv run chromium-search-migrator \
  "$HOME/Library/Application Support/Arc/User Data/Default/Web Data" \
  "$HOME/Library/Application Support/Google/Chrome/Default/Web Data" \
  --apply
```

List entries that would be imported:

```sh
uv run chromium-search-migrator source-web-data target-web-data --list
```

## Safety

- Only imports source rows with `is_active = 1`.
- Skips rows when the target already has the same `keyword`.
- Skips rows when the target already has the same `url`.
- Regenerates `sync_guid` for imported rows.
- Creates a backup in `/tmp` before writing, unless `--no-backup` is set.
- Runs `PRAGMA integrity_check` after writing.

Close the target browser before applying changes, otherwise the database may be locked.
