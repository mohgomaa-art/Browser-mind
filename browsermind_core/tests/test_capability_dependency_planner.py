"""
P7G-A direct chain test — verifies that search_email -> read_email
dependency is detected when both capabilities exist in the graph.
"""
import sys
sys.path.insert(0, '.')

from browsermind_core.ontology.asset import AssetGraph
from browsermind_core.agent.capability_dependency_planner import CapabilityDependencyPlanner


def build_manual_graph():
    """Build a graph that contains search_email and read_email capabilities directly."""
    g = AssetGraph()

    # Environments
    g.add_node('gmail', 'Environment', {'kind': 'email_client'})

    # AssetInstances (externally provided)
    g.add_node('gmail_primary', 'AssetInstance', {'asset_type': 'email_account'})
    g.add_node('email_account', 'AssetType', {})
    g.add_node('query', 'AssetType', {})  # search query is provided externally by user

    # Capabilities - the critical chain
    g.add_node('search_email', 'Capability', {
        'inputs': ['email_account', 'query'],
        'outputs': ['email_id'],
        'consumes_state': [],
        'produces_state': ['email.selected'],
        'description': 'Search inbox'
    })
    g.add_node('read_email', 'Capability', {
        'inputs': ['email_account', 'email_id'],
        'outputs': ['email_content'],
        'consumes_state': ['email.selected'],
        'produces_state': ['email.opened'],
        'description': 'Read email body'
    })

    # Also add a wallet chain
    g.add_node('stripe_wallet', 'Environment', {'kind': 'wallet'})
    g.add_node('payment_asset', 'AssetType', {})
    g.add_node('visa_personal', 'AssetInstance', {'asset_type': 'payment_asset'})
    g.add_node('charge_payment', 'Capability', {
        'inputs': ['payment_asset'],
        'outputs': ['receipt_id', 'payment_status'],
        'consumes_state': [],
        'produces_state': ['checkout.payment_processed'],
        'description': 'Process payment'
    })
    g.add_node('read_billing_info', 'Capability', {
        'inputs': ['payment_asset'],
        'outputs': ['billing_info'],
        'consumes_state': [],
        'produces_state': ['wallet.billing_info_loaded'],
        'description': 'Read billing address'
    })

    # Supports edges
    g.add_edge('gmail', 'search_email', 'supports')
    g.add_edge('gmail', 'read_email', 'supports')
    g.add_edge('stripe_wallet', 'charge_payment', 'supports')
    g.add_edge('stripe_wallet', 'read_billing_info', 'supports')

    return g


def main():
    print('=' * 60)
    print('  P7G-A  Capability Chain Unit Test')
    print('=' * 60)

    g = build_manual_graph()
    planner = CapabilityDependencyPlanner()
    result = planner.plan(g)

    print('\nDependency paths found:')
    if result.dependency_paths:
        for provider, consumer in result.dependency_paths:
            print('  ' + provider + ' -> ' + consumer)
    else:
        print('  (none)')

    print('\nUnsatisfied states:')
    if result.unsatisfied_states:
        for state in result.unsatisfied_states:
            print('  ' + state)
    else:
        print('  (none - all required states are produced)')

    print('\nUnsatisfied inputs (assets/data):')
    if result.unsatisfied_inputs:
        for inp in result.unsatisfied_inputs:
            print('  ' + inp)
    else:
        print('  (none - all inputs are provided by assets)')

    print('\nSummary: ' + str(result.summary()))

    # Assertions
    assert ('search_email', 'read_email') in result.dependency_paths, \
        'FAIL: search_email -> read_email chain not detected'
    assert not result.cycles_detected, 'FAIL: cycle detected'
    assert result.max_depth >= 1, 'FAIL: max_depth should be >= 1'
    assert not result.unsatisfied_states, \
        'FAIL: all consumed states should be satisfied, got: ' + str(result.unsatisfied_states)
    assert not result.unsatisfied_inputs, \
        'FAIL: all inputs should be covered by assets, got: ' + str(result.unsatisfied_inputs)

    print('\n[PASS] All assertions passed')
    print('[PASS] search_email -> read_email chain correctly identified')
    print('[PASS] No cycles, DAG is valid')


if __name__ == '__main__':
    main()
