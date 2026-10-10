import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.maintenance.synthetic_record_inventory import SMOKE_MARKER, build_inventory
from app.models import Assessment, ConnectorConfig, Customer, Organization


def test_inventory_reports_only_aggregate_smoke_candidates_without_mutating(db_session: Session):
    real_customer = Customer(name="Real Customer", slug="real-customer", status="active")
    smoke_customer = Customer(
        name="Smoke Customer 20261010",
        slug="smoke-customer-20261010",
        contact_name="Smoke Tester",
        contact_email="smoke@example.local",
        status="active",
        notes=SMOKE_MARKER,
    )
    db_session.add_all([real_customer, smoke_customer])
    db_session.flush()

    smoke_organization = Organization(
        customer_id=smoke_customer.id,
        name="Smoke Test Org 20261010",
        description=SMOKE_MARKER,
    )
    real_organization = Organization(
        customer_id=real_customer.id,
        name="Production Workspace",
        description="Customer-owned record",
    )
    db_session.add_all([smoke_organization, real_organization])
    db_session.flush()
    db_session.add_all(
        [
            ConnectorConfig(
                organization_id=smoke_organization.id,
                display_name="Smoke Google Workspace",
                status="connection_failed",
            ),
            Assessment(
                organization_id=smoke_organization.id,
                title="Smoke assessment 20261010",
                status="draft",
            ),
        ]
    )
    db_session.commit()

    customer_count_before = db_session.scalar(select(func.count()).select_from(Customer))
    report = build_inventory(db_session)
    serialized_report = json.dumps(report)

    assert report["candidate_groups"][0]["record_count"] == 1
    assert report["candidate_groups"][1]["record_count"] == 1
    assert report["associated_data"]["connector_configs"] == 1
    assert report["associated_data"]["assessments"] == 1
    assert report["cleanup_eligibility"] == "eligible_for_manual_review_only"
    assert report["safe_to_delete_now"] is False
    assert "20261010" not in serialized_report
    assert "Production Workspace" not in serialized_report
    assert db_session.scalar(select(func.count()).select_from(Customer)) == customer_count_before


def test_inventory_requires_manual_review_for_credential_bearing_candidate(db_session: Session):
    customer = Customer(
        name="Smoke Customer 20261011",
        slug="smoke-customer-20261011",
        contact_name="Smoke Tester",
        contact_email="smoke@example.local",
        status="active",
        notes=SMOKE_MARKER,
    )
    db_session.add(customer)
    db_session.flush()
    organization = Organization(
        customer_id=customer.id,
        name="Smoke Test Org 20261011",
        description=SMOKE_MARKER,
    )
    db_session.add(organization)
    db_session.flush()
    db_session.add(
        ConnectorConfig(
            organization_id=organization.id,
            display_name="Google Workspace",
            status="connected",
            credential_ref="managed/hidden.json",
        )
    )
    db_session.commit()

    report = build_inventory(db_session)

    assert report["associated_data"]["credential_bearing_connector_configs"] == 1
    assert report["cleanup_eligibility"] == "manual_review_required_credentials_present"
    assert report["safe_to_delete_now"] is False
