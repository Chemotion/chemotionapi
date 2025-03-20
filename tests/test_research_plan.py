from chemotion_api import Instance
from chemotion_api.elements.research_plan import ResearchPlan, RichText
from chemotion_api.collection import Collection


def test_create(instance_with_collection: dict):
    logged_in_instance :Instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    rs_1: ResearchPlan = col.new_research_plan()
    rs_1.add_image('../test_config/sample_files/kadi.png')
    rs_1.add_richtext('Super Text')
    table = rs_1.add_table()
    t_id = table.id
    rs_1.add_richtext(at_idx=0).add_text("Main Header", header=RichText.HeaderType.H2)

    name_col_id, age_col_id = table.add_columns("Name", "Age")
    table.add_columns("Is Developer")
    table.add_row('Mr. X', False, **{age_col_id: 30}).add_row('Mr. Y')
    table.set_entry(1, age_col_id, 40)
    age_average = sum(table.get_column(age_col_id)) / len(table)
    assert age_average == 35
    rs_1.save()
    rs = logged_in_instance.get_research_plan(rs_1.id)
    table_reloaded = next(x for x in rs.body if x['id'] == t_id)
    assert rs.body[3] == table_reloaded

    age_average = sum(table_reloaded.get_column(age_col_id)) / len(table)
    assert age_average == 35
    assert table_reloaded.get_column(name_col_id) == ['Mr. X', 'Mr. Y']
    try:
        rs.attachments.load_attachment(7)
    except:
        pass
    rs.attachments.add_file('../test_config/sample_files/20200702_dcm_PH884_100_red2.DTA')
    rs.save()