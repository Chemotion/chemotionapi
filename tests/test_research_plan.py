from chemotion_api import Instance
from chemotion_api.elements.research_plan import ResearchPlan
from chemotion_api.collection import Collection


def test_create(instance_with_collection: dict):
    logged_in_instance :Instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    rs_1: ResearchPlan = col.new_research_plan()
    rs_1.add_image('../test_config/sample_files/kadi.png')
    rs_1.add_richtext('Super Text')
    rs_1.add_table()
    rs_1.save()
    rs = logged_in_instance.get_research_plan(1)
    try:
        rs.attachments.load_attachment(7)
    except:
        pass
    rs.attachments.add_file('../test_config/sample_files/20200702_dcm_PH884_100_red2.DTA')
    rs.save()