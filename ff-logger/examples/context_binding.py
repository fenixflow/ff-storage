#!/usr/bin/env python3
"""
Example demonstrating context binding in ff-logger.

As of v0.3.0, bind() modifies the logger in place rather than creating
a new instance, making it simpler and more intuitive to use.

Created by Ben Moag (Fenixflow)
"""

from ff_logger import ConsoleLogger, JSONLogger


def main():
    # Create base logger with application-wide context
    app_logger = ConsoleLogger(
        name="payment_service",
        level="INFO",  # String levels supported in v0.3.0+
        context={"service": "payment-api", "version": "1.0.0", "environment": "production"},
    )

    app_logger.info("Payment service started")
    # Output includes: service="payment-api" version="1.0.0" environment="production"

    # Simulate processing a user request
    user_id = "user-12345"
    request_id = "req-67890"

    # Add request-specific context (modifies logger in place as of v0.3.0)
    app_logger.bind(request_id=request_id, user_id=user_id, ip_address="192.168.1.100")

    app_logger.info("Processing payment request")
    # Output includes all context

    # Process different payment methods
    # Note: We pass the same logger, which now has request context
    process_credit_card(app_logger, card_last_four="1234")
    process_paypal(app_logger, paypal_email="user@example.com")

    # Errors maintain full context chain
    try:
        risky_payment_operation()
    except Exception as e:
        app_logger.error("Payment processing failed", error=str(e), payment_method="credit_card")

    # Demonstrate JSON logger with context binding
    json_logger = JSONLogger(
        name="audit",
        level="info",  # Case-insensitive in v0.3.0+
        context={"audit": True, "compliance": "PCI-DSS"},
    )

    # Add transaction context (modifies in place, returns self for chaining)
    json_logger.bind(transaction_id="txn-abc123", amount=99.99, currency="USD").info(
        "Transaction initiated"
    )  # Can chain!

    json_logger.info("Transaction completed", status="success")


def process_credit_card(logger, card_last_four):
    """Process credit card payment with card-specific logging context."""
    # Add payment method context (temporarily - for this function only)
    # Note: In v0.3.0, bind() modifies in place, so we should save/restore
    # context if we don't want it to persist
    original_context = logger.context.copy()
    logger.bind(payment_method="credit_card", card_last_four=card_last_four)

    logger.info("Validating credit card")
    logger.info("Charging credit card")
    logger.info("Credit card charged successfully")

    # Restore original context
    logger.context = original_context


def process_paypal(logger, paypal_email):
    """Process PayPal payment with PayPal-specific logging context."""
    # Add payment method context temporarily
    original_context = logger.context.copy()
    logger.bind(payment_method="paypal", paypal_account=paypal_email)

    logger.info("Redirecting to PayPal")
    logger.info("PayPal authorization received")
    logger.info("PayPal payment completed")

    # Restore original context
    logger.context = original_context


def risky_payment_operation():
    """Simulate an operation that might fail."""
    raise ValueError("Insufficient funds")


if __name__ == "__main__":
    main()
