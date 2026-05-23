from domain_core.registry import get_domain_spec


def test_deposit_has_party_role_labels():
    spec = get_domain_spec("housing.deposit.v1")
    assert spec.party_role_labels["tenant"]["label"] == "Tenant"
    assert spec.party_role_labels["landlord"]["label"] == "Landlord"


def test_employment_labels_humanise_machine_roles():
    spec = get_domain_spec("employment.unfair_dismissal.v1")
    assert spec.party_role_labels["claimant"]["label"] == "Employee (claimant)"
    assert spec.party_role_labels["respondent_employer"]["label"] == "Employer (respondent)"


def test_every_labelled_role_is_a_real_party_role():
    for did in [
        "housing.deposit.v1", "housing.property_chamber.rro.v1",
        "housing.rent_determination.v1", "housing.repairs_social.v1",
        "employment.unfair_dismissal.v1",
    ]:
        spec = get_domain_spec(did)
        assert spec.party_role_labels, f"{did} missing party_role_labels"
        for role in spec.party_role_labels:
            assert role in spec.party_roles, f"{did}: {role} not in party_roles"
