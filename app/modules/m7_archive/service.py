from app.modules.m7_archive.export_out import checksum


def execute(state):
    state['archive'] = {
        'sha256': checksum(state),
        'evidence_count': (len(state.get('calculations', [])) + len(state['quarantine'])
                           + len(state.get('held_rows', [])) + len(state.get('name_decisions', []))),
        'ready': state.get('reconcile', {}).get('balanced', False),
    }
    return state
