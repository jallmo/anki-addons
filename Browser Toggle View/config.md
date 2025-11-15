# Document Toggle Browser

This add-on replaces the Browser table with a clean stacked document view.  
Add the two browser columns referenced below (defaults match the screenshot: *Question* and *Answer*).  
Use **View → Toggle Document View** or the shortcut defined in `hotkey_toggle_document_view`
to flip between the standard table and the inline document.

## Config keys

* `question_column_header` – Header text (exact match, case-sensitive) that should be treated as the question.
* `answer_column_header` – Header text for the answer column.
* `question_field_name` / `answer_field_name` – Reserved for future editing features. Leave blank to reuse the column headers.
* `max_rows` – Maximum number of rows to materialize into the document view. Keep the number modest to avoid lag.
* `hotkey_toggle_document_view` – Shortcut used from anywhere inside the browser window to open/focus the document view.

> Tip: If you rename the browser columns, update the config to the new names to keep the document view in sync.
