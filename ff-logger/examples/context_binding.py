#!/usr/bin/env python3
"""
Example demonstrating context binding in ff-logger.

Context binding allows you to create scoped loggers with permanent fields
that are included in every log message.

Created by Ben Moag (Fenixflow)
"""

import logging

from ff_logger import ConsoleLogger, JSONLogger


def main():
    # Create base logger with application-wide context
    app_logger = ConsoleLogger(
        name="payment_service",
        level=logging.INFO,
        context={"service": "payment-api", "version": "1.0.0", "environment": "production"},
    )

    app_logger.info("Payment service started")
    # Output includes: service="payment-api" version="1.0.0" environment="production"

    # Simulate processing a user request
    user_id = "user-12345"
    request_id = "req-67890"

    # Create request-scoped logger with additional context
    request_logger = app_logger.bind(
        request_id=request_id, user_id=user_id, ip_address="192.168.1.100"
    )

    request_logger.info("Processing payment request")
    # Output includes all parent context plus request-specific context

    # Process different payment methods with method-specific context
    process_credit_card(request_logger, card_last_four="1234")
    process_paypal(request_logger, paypal_email="user@example.com")

    # Errors maintain full context chain
    try:
        risky_payment_operation()
    except Exception as e:
        request_logger.error(
            "Payment processing failed", error=str(e), payment_method="credit_card"
        )

    # Demonstrate JSON logger with context binding
    json_logger = JSONLogger(
        name="audit", level=logging.INFO, context={"audit": True, "compliance": "PCI-DSS"}
    )

    # Create transaction-scoped logger
    transaction_logger = json_logger.bind(transaction_id="txn-abc123", amount=99.99, currency="USD")

    transaction_logger.info("Transaction initiated")
    transaction_logger.info("Transaction completed", status="success")


def process_credit_card(logger, card_last_four):
    """Process credit card payment with card-specific logging context."""
    # Create payment method scoped logger
    card_logger = logger.bind(payment_method="credit_card", card_last_four=card_last_four)

    card_logger.info("Validating credit card")
    card_logger.info("Charging credit card")
    card_logger.info("Credit card charged successfully")


def process_paypal(logger, paypal_email):
    """Process PayPal payment with PayPal-specific logging context."""
    # Create payment method scoped logger
    paypal_logger = logger.bind(payment_method="paypal", paypal_account=paypal_email)

    paypal_logger.info("Redirecting to PayPal")
    paypal_logger.info("PayPal authorization received")
    paypal_logger.info("PayPal payment completed")


def risky_payment_operation():
    """Simulate an operation that might fail."""
    raise ValueError("Insufficient funds")


if __name__ == "__main__":
    main()
