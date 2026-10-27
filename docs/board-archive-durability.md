# Durable completed-board archives

Staging uses the fixed table name `bridge-staging-board-archives`, configured
through `BOARD_ARCHIVES_TABLE`. Lambda deployments must set this variable.
The table has partition key
`roomId` (String) and sort key `boardNumber` (Number), on-demand billing, and no
indexes or TTL. Do not enable expiration: archives must survive room cleanup.
Archive items wrap the immutable replay record in `board`. Access by board ID
uses a strongly consistent, paginated room-partition query; numeric board lists
use a strongly consistent descending query. No table scan is required.

At cold initialization call
`lambdas.core.game.archives.configure_from_environment()`, after configuring
`duplicate.store` as `duplicate.DynamoEventStore` against the table identified
by `DUPLICATE_EVENTS_TABLE` (partition key `eventId`, String). The game runtime
also checks archive configuration when saving or reading records. Local servers
without Lambda environment variables retain the explicit in-memory adapter.
Missing Lambda archive configuration or a missing durable duplicate adapter fails
closed, rather than silently publishing to process-local memory.
In Lambda, the archive initialization hook also requires `DUPLICATE_EVENTS_TABLE`
and verifies that the initialized event adapter targets that exact table.

`runtime.save_room` commits completed room state (including cumulative scores),
the immutable archive, and any duplicate-event result in one DynamoDB transaction.
Each item uses a conditional write. Concurrent completions at different event
tables reread and retry the event revision up to five times; a stale room revision
returns a conflict. An archive mismatch aborts the entire transaction. Retrying
an identical completion neither duplicates match scores nor event results.
There is no asynchronous completion outbox or additional completion worker.

All relevant game, room lifecycle, and tick Lambdas need `dynamodb:PutItem` and
`dynamodb:Query` on the archive table; `dynamodb:PutItem` on rooms; and
`dynamodb:GetItem` / `dynamodb:PutItem` on duplicate events. Transactional writes
are authorized by `dynamodb:PutItem` for every participating table (there is no
separate IAM `dynamodb:TransactWriteItems` action). Existing room/auth/connection
read permissions remain necessary. Infrastructure must explicitly provision and
grant this table before enabling the routes.

WebSocket notification remains best-effort after commit, as before: reconnect or
snapshot reads recover the durable state. Historical boards already lost from a
previous in-memory deployment cannot be reconstructed. Archive lookup by board
ID is linear in that room's retained board count; numeric pagination is indexed
by the primary key. DynamoDB item/transaction size limits apply; oversized
records fail without partially committing completion.
