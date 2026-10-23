"""Failed field merges cannot leak into an enclosing caller transaction."""
import pytest

from test_shared_labels import make_linked_project, file_endpoint, memory_endpoint


def test_failed_merge_inside_existing_transaction_keeps_both_original_identities(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        project.rename_file('save-a.dat', 8, 'saved_food')
        project.annotate(data, 'live_food', kind='name')
        before = project.label_info(file_endpoint())
        with project.transaction(True):
            with pytest.raises(ValueError, match='conflicting explicit'):
                project.link_labels(file_endpoint(), memory_endpoint(data), size=8,
                                    evidence='Deliberately unresolved name conflict.')
            assert project.label_info(file_endpoint()) == before
        assert project.label_info(file_endpoint()) == before
        assert project.label_info(memory_endpoint(data))['name'] == 'live_food'


def test_whole_block_merge_checks_conflicts_on_interior_fields(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        project.rename_file('save-a.dat', 10, 'saved_restrooms')
        project.annotate(data+2, 'live_restrooms', kind='name')
        with pytest.raises(ValueError, match='conflicting explicit'):
            project.link_labels(file_endpoint(), memory_endpoint(data), size=8,
                                name='food_count', evidence='Name resolves only the first field.')
        assert project.label_info(file_endpoint())['links'] == []
        assert project.label_info(file_endpoint('save-a.dat', 10))['name'] == 'saved_restrooms'
