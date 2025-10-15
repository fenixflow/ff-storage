"""
Test PostgreSQL parameter handling to ensure no 'dict is not a sequence' errors.
"""

import unittest
from unittest.mock import MagicMock

from ff_storage.db.connections.postgres import PostgresBase


class TestPostgresParameterHandling(unittest.TestCase):
    """Test that PostgreSQL methods handle None params correctly."""

    def setUp(self):
        """Set up test fixtures."""
        self.postgres = PostgresBase(
            dbname="test_db", user="test_user", password="test_pass", host="localhost", port=5432
        )
        # Mock the connection and cursor
        self.mock_cursor = MagicMock()
        self.mock_connection = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.postgres.connection = self.mock_connection

    def test_read_query_with_none_params(self):
        """Test read_query passes None params correctly to psycopg2."""
        query = "SELECT * FROM users"
        self.mock_cursor.fetchall.return_value = [("test",)]

        result = self.postgres.read_query(query, None, as_dict=False)

        # Verify cursor.execute was called with None (not {})
        self.mock_cursor.execute.assert_called_once_with(query, None)
        self.assertEqual(result, [("test",)])

    def test_read_query_without_params(self):
        """Test read_query with no params argument."""
        query = "SELECT * FROM users"
        self.mock_cursor.fetchall.return_value = [("test",)]

        result = self.postgres.read_query(query, as_dict=False)

        # Verify cursor.execute was called with None (not {})
        self.mock_cursor.execute.assert_called_once_with(query, None)
        self.assertEqual(result, [("test",)])

    def test_read_query_with_dict_params(self):
        """Test read_query with actual dict params."""
        query = "SELECT * FROM users WHERE id = %(id)s"
        params = {"id": 123}
        self.mock_cursor.fetchall.return_value = [("test",)]

        result = self.postgres.read_query(query, params, as_dict=False)

        # Verify cursor.execute was called with the dict
        self.mock_cursor.execute.assert_called_once_with(query, params)
        self.assertEqual(result, [("test",)])

    def test_execute_with_none_params(self):
        """Test execute passes None params correctly to psycopg2."""
        query = "UPDATE users SET active = true"

        self.postgres.execute(query, None)

        # Verify cursor.execute was called with None (not {})
        self.mock_cursor.execute.assert_called_once_with(query, None)
        self.mock_connection.commit.assert_called_once()

    def test_execute_without_params(self):
        """Test execute with no params argument."""
        query = "DELETE FROM expired_sessions"

        self.postgres.execute(query)

        # Verify cursor.execute was called with None (not {})
        self.mock_cursor.execute.assert_called_once_with(query, None)
        self.mock_connection.commit.assert_called_once()

    def test_execute_with_dict_params(self):
        """Test execute with actual dict params."""
        query = "UPDATE users SET name = %(name)s WHERE id = %(id)s"
        params = {"name": "John", "id": 123}

        self.postgres.execute(query, params)

        # Verify cursor.execute was called with the dict
        self.mock_cursor.execute.assert_called_once_with(query, params)
        self.mock_connection.commit.assert_called_once()

    def test_execute_query_with_none_params(self):
        """Test execute_query passes None params correctly to psycopg2."""
        query = "INSERT INTO users (name) VALUES ('test') RETURNING id"
        self.mock_cursor.fetchall.return_value = [(1,)]

        result = self.postgres.execute_query(query, None)

        # Verify cursor.execute was called with None (not {})
        self.mock_cursor.execute.assert_called_once_with(query, None)
        self.mock_connection.commit.assert_called_once()
        self.assertEqual(result, [(1,)])

    def test_execute_query_without_params(self):
        """Test execute_query with no params argument."""
        query = "DELETE FROM old_records RETURNING count(*)"
        self.mock_cursor.fetchall.return_value = [(5,)]

        result = self.postgres.execute_query(query)

        # Verify cursor.execute was called with None (not {})
        self.mock_cursor.execute.assert_called_once_with(query, None)
        self.mock_connection.commit.assert_called_once()
        self.assertEqual(result, [(5,)])

    def test_execute_query_with_dict_params(self):
        """Test execute_query with actual dict params."""
        query = "INSERT INTO users (name, email) VALUES (%(name)s, %(email)s) RETURNING id"
        params = {"name": "John", "email": "john@example.com"}
        self.mock_cursor.fetchall.return_value = [(1,)]

        result = self.postgres.execute_query(query, params)

        # Verify cursor.execute was called with the dict
        self.mock_cursor.execute.assert_called_once_with(query, params)
        self.mock_connection.commit.assert_called_once()
        self.assertEqual(result, [(1,)])

    def test_no_dict_is_not_sequence_error(self):
        """
        Test that None params don't cause 'dict is not a sequence' error.

        This test simulates what happens when psycopg2 receives an empty dict
        for a query without named placeholders - it would raise TypeError.
        """
        query = "SELECT * FROM users WHERE active = true"

        # Simulate psycopg2 behavior: empty dict with non-named query would error
        def mock_execute(q, params):
            if params == {} and "%" not in q:
                raise TypeError("dict is not a sequence")
            return None

        self.mock_cursor.execute.side_effect = mock_execute
        self.mock_cursor.fetchall.return_value = []

        # This should NOT raise an error because we pass None, not {}
        result = self.postgres.read_query(query, as_dict=False)

        # Should have been called with None, avoiding the error
        self.mock_cursor.execute.assert_called_once_with(query, None)
        # Result is used to ensure the query completes
        assert result == []


if __name__ == "__main__":
    unittest.main()
