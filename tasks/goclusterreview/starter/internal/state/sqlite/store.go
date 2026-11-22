package sqlite

import "database/sql"

type Store struct{ db *sql.DB }
