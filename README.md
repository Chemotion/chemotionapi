# ChemotionApi

| PLEASE NOTICE: This version is far from beeing ready. |
|-------------------------------------------------------|
## Open ToDos
<ul> 
<li>The generic elements section is not implemented </li>
<li>The research plan section is not implemented </li>
<li>The admin functions are not implemented </li>
<li>Create dataset function is not implemented </li>
<li>Share and Sync functions are not implemented </li>
</ul> 

A python api for [Chemotion](https://chemotion.net/). Chemotion is a Electronic Laboratory Notebook (ELN) developed at
the KIT is a web-based platform designed to help researchers manage and organize their experimental data in a secure and
efficient manner.

The ChemotionApi Python package is a wrapper for the RESTful API built on top of the Ruby on Rails
framework that allows users to interact with Chemotion ELN. The package provides a simple and intuitive
interface for creating, retrieving, updating, and deleting data stored in the ELN using Python. With
its RESTful architecture and comprehensive documentation, the ChemotionApi allows users to build custom applications and
workflows that leverage the ELN's capabilities and streamline their research processes.

# Installation

At the moment this package has not been daploayed to **PyPI**.To install, simply clone the package to a directory of
your choice:

```shell
git clone https://github.com/StarmanMartin/ChemotionApi.git
cd ChemotionApi
```

To build and install this package we use [Poetry](https://python-poetry.org/). Hence, if you want to install it poetry
has to be installed on your system (howto [here](https://python-poetry.org/docs/)).
To build it simpy go into the directory ad execute

```shell
poetry install #to install all dependencies
poetry build
pip install <abspath_to_ChemotionApi_zip> # most likely in the dist directory
```

# Usage

In order for the API to work, a connection to a Chmotion instance must first be established.
For this purpose a object of the type _Instance_ must be initialized. This object gets the
host URL passed to it as a string.

```python
from chemotion_api import Instance

URL = "http(s)://xxx.xxx.xxx/"

instance = Instance(URL)

```

You can check if the connection works b<y:

```python
try:
    instance.test_connection()
except:
    print('Connection failed!')
```

Almost all functions provided by this API require a successful login first:

```python
try:
    instance.login('<USER>', '<PASSWORD>')
except:
    print('login failed!')
```

After the instance is logged in, different functions are available
depending on the user type and rights. Following come the admin
function and then the functions of a standard user.

## Admin Basics

**ToDo**

## User Basics

The main function offered to standard user are used to read,
edit, create or delete elements such
as [Samples](https://chemotion.net/docs/eln/ui/elements/samples), [Reactions](https://chemotion.net/docs/eln/ui/elements/reactions),
 [Research Plans](https://chemotion.net/docs/eln/ui/details_modal?_highlight=research#detail-modal-for-research-plan),
[Wellplates](https://chemotion.net/docs/eln/ui/elements/wellplates)
and/or [Generic elements](https://chemotion.net/docs/eln/admin/generic_config).
However, the basic workflow with chemotion divides the elements of the projects into
so-called [collections](https://chemotion.net/docs/eln/ui/collections).
Hence, most of the element related function are outsourced to a Collection object. Only getting single elements based on
a ID
can be fetched from the _instance_ object. To fetch a Sample:

```python
try:
    sample = instance.get_sample(1)  # Let 1 be the id of a sample in this example
except:
    print('No Sample could be fetched')
```

To Fetch a Reaction:

```python
try:
    reaction = instance.get_reaction(1)  # Let 1 be the id of a reaction in this example
except:
    print('No Sample could be fetched')
```

To Fetch a Wellplate:

```python
try:
    wellplate = instance.get_wellplate(1)  # Let 1 be the id of a wellplate in this example
except:
    print('No Sample could be fetched')
```

To Fetch a Research Plan:

```python
try:
    research_plan = instance.get_research_plan(1)  # Let 1 be the id of a research plan in this example
except:
    print('No Sample could be fetched')
```

In the section [Elements](#elements) we show what you can do with the retrieved elements. First, however, we will explain how to use the collections.

### Collections

Collections are the main principle in Chemotion to organize your project. To work with the collections, you must always get the
collection root object first:

```python
from chemotion_api.collection import RootCollection

root_collection: RootCollection = instance.get_root_collection()
```

The _root_collection_ objects enables you to manage all your collections. To address a collection use simple linux path description. The first following code snippet shows how to create an new collection:

```python
from chemotion_api.collection import RootCollection, Collection

root_collection: RootCollection = instance.get_root_collection()

# Creates a collection at the path /Col1
col_1: Collection = root_collection.get_or_create_collection('/Col1')
# Creates a collection at the path /Col1/Col2 
col_2: Collection = root_collection.get_or_create_collection('Col1/Col2')
```

If the path is absolute _i.e._ it starts with "/" it creates the collection starting from your root path. 
Hence, it makes no difference to use an absolute path or a relative path in your _root_collection_ object. However, 
you can create collections also in another collection object. In this case you should use a relative path otherwise 
it again uses the _root_collection_ as stating point to create a new collection:

```python
# Creates a collection at the path /Col1/Col2/Col3
col_3: Collection = col_2.get_or_create_collection('Col3')
# Creates a collection at the path /Col4
col_4: Collection = col_1.get_or_create_collection('/Col4')
```

To navigate through ypur collections you need to either use the _get_or_create_collection_ function or the _get_collection_ function.
But be aware that _get_collection_ will throw an error if the path does not exist.

```python
col_2_a: Collection = root_collection.get_collection('/Col1/Col2')
col_2_b: Collection = col_1.get_collection('Col2')

try:
    x = col_1.get_collection('XXX')
except:
    print('The collection "XXX" does not exist!')

assert col_2.id == col_2_a.id
assert col_2.id == col_2_b.id

```

All collection can be used to get all elements of a type maintained by itself as an ElementSet object as in the following example:

```python
from chemotion_api.elements import ElementSet

per_page = 5
# To get all samples
samples: ElementSet = root_collection.get_samples(per_page=per_page)
# To get all samples in col_1
samples_col_1: ElementSet = col_1.get_samples(per_page=per_page)
# To get all reactions
reactions: ElementSet = root_collection.get_reactions(per_page=per_page)
# To get all wellplates
wellplate: ElementSet = root_collection.get_wellplates(per_page=per_page)
# To get all research plans
research_plan: ElementSet = root_collection.get_research_plans(per_page=per_page)
```

The getter in the _root_collection_ get all of teh ellements of a type as in the 
"[All](https://chemotion.net/docs/eln/ui/collections#standard-collections-all-and-chemotion-repositorynet)" collection.

Please notice that these getter have an optional parameter _per_page_. Since the system would most likely crash if you would fetch too many elements of a type at once, it fetches only a certain number at the time.
The _per_page_ parameter specifies the numer of fetched elements.
To iterate over all Elements you can use the following:

```python
with [] as ids:
    for s in samples.iter_pages():
        assert len(s) <= per_page
        for sample in s:
            assert sample.id not in ids
            ids.append(sample.id)

    s = samples.prev_page()  # Returns previous page if it exists else it has no effect
    for sample in s:
        assert sample.id in ids
        assert len(s) <= per_page

    s = samples.next_page()  # Returns next page if it exists else it has no effect
    for sample in s:
        assert sample.id in ids
        assert len(s) <= per_page

```

You can rename a collection you need to rename the label attribute of a collection object and save it. To save a collection you have to use the _save_ function of the _root_collection_:
```python
# Rename the collection to Col1A
col_1.lable += 'A'
# Save all changes
root_collection.save()
```

Note that from now on the path of all sub-collections of Col1A change to /Col1A/...

Collection can also be moved into other collection. To move a collection either use the _move_ function of a collection object or use a global move function of the _root_collection_:

```python
# Move Col4 into Col1A
col_4.move('/Col1A')
# Save all changes
root_collection.save()
# Move it back
root_collection.move('/Col1A/Col4', '/')
# Save all changes
root_collection.save()
```


Finally, we explain how you can delete a collection. Each non-root collection can be deleted by its _delete_ function or the _delete_ function of the _root_collection_ with a path.

```python
# To delete Col4
col_4.delete()
# To delete /Col1/Col2
root_collection.delete('/Col1A/Col2')
# Save all changes
root_collection.save()
```


### Elements

To interact with the elements (_e.g._, [Samples](https://chemotion.net/docs/eln/ui/elements/samples), [Reactions](https://chemotion.net/docs/eln/ui/elements/reactions),
[Research Plans](https://chemotion.net/docs/eln/ui/details_modal?_highlight=research#detail-modal-for-research-plan),
[Wellplates](https://chemotion.net/docs/eln/ui/elements/wellplates)
and/or [Generic elements](https://chemotion.net/docs/eln/admin/generic_config)),
you can use the corresponding objects obtained from the instance or the collection. Here are some examples how to obtain the objects:


```python
# To get an element by its ID use the instance object
sample = instance.get_sample(1)
# To get all elements in a collection use the collection object
# Set the parameter reload to 'false' to prevent unnecessary data-loading 
samples = instance.get_root_collection(reload=False).get_collection('Col1A').get_samples() 
```

See [User Basics](#user-basics) or [Collections](#collections) on how to fetch other types than Samples. 
All types of element (samples, reactions, research plans, wellplates, and/or general elements), have some common basic properties.
We will introduce these common properties based on the sample object first. After this introduction of the common functions we go into the individual features of the objects. 

Each element has the _json_data_ object. It contains the origen data fetched from the server and should NOT be manipulated by you.
Instead, you can use the preprocessed objects _properties_, _analyses_ and _segments_. The _properties_ is a simple [dict](https://docs.python.org/3/tutorial/datastructures.html#dictionaries) and _analyses_ is a list of extended [dicts](https://docs.python.org/3/tutorial/datastructures.html#dictionaries) objects.
To change simple properties of an element permanently you simply change the value in the dicts and then save the object:


| WARNING: be careful the data you change will not be validated by the AIP! |
|------------------------------------------------------------------------------------------------------------------|

```python
# The boiling point lowerbound is a simple float 
sample.properties['boiling_point_lowerbound'] = 99.5
# The boiling point upperbound is a simple float 
sample.properties['boiling_point_upperbound'] = 100.5
# The boiling point upperbound is a system value (it has a value and a unit)
sample.properties['target_amount']['value'] = 5
sample.properties['target_amount']['unit'] = 'g'
# And we also change the name of the first analyses of the sample (must exist) analyses
sample.analyses[-1]['name'] = 'My Sample analyses'
sample.save()
```

To see all possible properties use something like:

```python
import json
print(json.dumps(sample.properties))
```

From the analyses objects we can fetch more complex data by using its extended properties such as:

```python
ana_1 = sample.analyses[-1]
# To download the preveiw image
with open('<path_to_svg_file>', 'wb') as f:
    f.write(ana_1.preview_image())
    
# To get the Dataset objects:
for dataset in ana_1.datasets:
    # Write all as ZIP
    dataset.write_zip('<path_to_zip_file>')
    # Write all as xlsx
    dataset.write_data_set_xlsx('<path_to_xlsx_file>')

```

A dataset is also an extended dict and can therefore be changed by simpley changing ist values:
```python
for idx, dataset in enumerate(ana_1.datasets):
    if 'name' in dataset:
        dataset['name'] = "DS # {}".format(idx)
# To commit your changes save the sample
sample.save()
```

Next we want to create a new element. 
Since any element has to be in a collection you have to call the create new-element function of a collection.

```python
# To create a new Sample
new_sample = col_1.new_sample()
# To create a new Reaction
new_reaction = col_1.new_reaction()
# To create a new Reasearch Plan
new_research_plan = col_1.new_research_plan()
# To create a new Wellplate
new_wellplate = col_1.new_wellplate()
```

Note that it is not automatically saved. You need to call the _save_ function to finally commit it.
Please make sure that all required properties are set before saving the object. We will recall them in the subsection about the individual element properties.


#### Sample Properties

A sample in Chemoition needs a molecule. Hence, you need to create a molecule first to save a new Sample.
To create a molecule you can use the molecule manager provided by the instance object.
So far two methodes are implemented to create a molecule object:

```python
# Create a molecule BH_3 by a smiles code
m = instance.molecule().create_molecule_by_smiles('B')
new_sample.molecule = m
# Cr create the same molecule BH_3 by a InChI code
m = instance.molecule().create_molecule_by_cls('BH3')
new_sample.molecule = m
new_sample.save()
```

The most common solvents are provided by Chemotion and can simply be created by the _new_solvent_ function.

```python
# For instance
solv = col_1.new_solvent('CDCl3')
solv.save()
```

To print a list of all provided solvents call:

```python
print(instance.get_solvent_list())
```
Another feature of Samples is the possibility of splitting.
Simply call the _split_ function to create a split of the origin sample.

```python
new_spit_sample = new_sampel.split()
new_spit_sample.save()
```

#### Reaction Properties

In order to work with a Reaction you must determine the materials required for the reaction.
The keys the materials in the properties dict of a reaction object are:
_starting_materials_, _reactants_, _products_, _solvents_ and _purification_solvents_.
These materials are represented as list object in the Reaction object. 
You can only add Sample objects to it. By adding a sample to the reaction materials
a new split of the sample is automatically created and added to the reaction.

```python
solv = col_1.new_solvent('CDCl3')
new_reaction.properties['starting_materials'].append(new_sampel)
new_reaction.properties['purification_solvents'].append(solv)
new_reaction.save()
```

#### Wellplate Properties

Wellplates have a new properies called wells. 
The singel wells of the wellplate can be addressed by a row number a column letter. 
You can only add Samples to the wells.
By adding a sample to a well a new split of the sample is automatically created and added to the well.

```python
new_wellplate.wells[0]['A'] = new_sample # from how to create samples
new_wellplate.wells[0]['b'] = solv # from how to create solvents
new_wellplate.wells[1]['b'] = sample # from how to fetch samples
new_wellplate.save()
```

#### Research Plan Properties

-> ToDo: Not jet implemented

## Contributing

Contributions to ChemotionApi are welcome! If you have any bug reports, feature requests, or suggestions, please
open an issue on the GitHub repository. You can also submit
pull requests with your proposed changes.

## License

ChemotionApi is licensed under the MIT License.

**Let me know if there's anything else I can help you with!**
