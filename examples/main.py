import json
import logging
import random



from chemotion_api import Instance
from examples.utils import load_config, CONFIG

if __name__ == '__main__':

    load_config()

    instance = Instance(CONFIG.get('ELN_URL')).test_connection().login(CONFIG.get('ELN_USER'), CONFIG.get('ELN_PASS'))
    user = instance.get_user()

    col = instance.get_root_collection()
    col.get_or_create_collection('/Martins')
    samples = col.get_collection('/Martins').get_samples()
    sample = instance.get_sample(187)
    sample.properties['boiling_point_lowerbound'] = '55.5'
    sample.properties['boiling_point_upperbound'] = '65.5'
    sample.properties['name'] = "Test Sample API"

    with open('Sample_Data/img.png', 'wb+') as f:
        img = sample.segments['Analyses'][0].preview_image()
        f.write(img)

    sample.segments.get('Object')['Sample history']['Sample label'] = "Test Label"
    try:
        sample.segments.get('Assay')
    except:
        print('OK')

    sample.segments['Enzyme methods data']['Additional information on the enzyme']['Tissue'] = 'Test'
    sample.segments['Enzyme methods data']['Assay conditions']['Buffer'].append(
        sample.segments['Enzyme methods data']['Assay conditions']['Buffer'][0].copy())
    sample.segments['Enzyme methods data']['Assay conditions']['Buffer'][-1]['Concentration']['value'] = int(
        random.random() * 500)
    sample.analyses[0].datasets[0]['General information']['title'] = 'Hallo Test Title'
    sample.analyses[0].datasets[0].write_data_set_xlsx("Sample_Data")
    sample.analyses[0].datasets[0].write_zip("Sample_Data")
    sample.save()

    col.get_collection('/External Collections/SPP Test Reactions/Test Collection Manuel Tsotsalas')

    col.move('/Martins/Inner Martins', '/External Collections/SPP Test Reactions/Test Collection Manuel Tsotsalas')

    a = col.get_collection('/External Collections/SPP Test Reactions/Test Collection Manuel Tsotsalas/Inner Martins')
    a.label += ' 2'
    col.save()

    a.move('../../../Martins')
    a = col.get_collection('/Martins/Inner Martins 2')
    a.label = 'Inner Martins'
    col.save()
