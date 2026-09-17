"""Source adapters. Each wraps one upstream (an SDK, a feed, an archive) and speaks only in
SourceBlocked / SourceDown / SourceChanged so modules can chain them."""
