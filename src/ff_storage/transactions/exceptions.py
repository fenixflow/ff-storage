"""
Exception classes for transaction management.

These exceptions provide clear error messages for common transaction-related
issues, helping developers identify and resolve problems quickly.
"""


class TransactionError(Exception):
    """
    Base exception for all transaction-related errors.

    All transaction-specific exceptions inherit from this class,
    allowing for broad exception handling when needed.
    """

    pass


class TransactionNotStarted(TransactionError):
    """
    Raised when attempting to use a transaction that hasn't been started.

    This typically occurs when:
    - Calling commit() or rollback() outside of a context manager
    - Accessing transaction.connection before entering the context
    """

    def __init__(self, message: str = "Transaction has not been started"):
        super().__init__(message)


class TransactionAlreadyStarted(TransactionError):
    """
    Raised when attempting to start a transaction that's already active.

    This can occur when:
    - Re-entering a transaction context manager
    - Calling start() multiple times on the same transaction
    """

    def __init__(self, message: str = "Transaction has already been started"):
        super().__init__(message)


class TransactionClosed(TransactionError):
    """
    Raised when attempting to use a transaction after it has been closed.

    A transaction is closed after:
    - Successful commit
    - Rollback
    - Exiting the context manager
    """

    def __init__(self, message: str = "Transaction has been closed"):
        super().__init__(message)


class SavepointError(TransactionError):
    """
    Base exception for savepoint-related errors.

    Savepoints are named points within a transaction that allow
    partial rollback without affecting the entire transaction.
    """

    pass


class SavepointNotFound(SavepointError):
    """
    Raised when attempting to rollback to a non-existent savepoint.

    This can occur when:
    - The savepoint name is misspelled
    - The savepoint was already released
    - The savepoint was in a rolled-back transaction
    """

    def __init__(self, savepoint_name: str):
        self.savepoint_name = savepoint_name
        super().__init__(f"Savepoint '{savepoint_name}' not found")


class SavepointAlreadyReleased(SavepointError):
    """
    Raised when attempting to use a savepoint that has been released.

    A savepoint is released when:
    - RELEASE SAVEPOINT is called explicitly
    - The savepoint context manager exits successfully
    """

    def __init__(self, savepoint_name: str):
        self.savepoint_name = savepoint_name
        super().__init__(f"Savepoint '{savepoint_name}' has already been released")
