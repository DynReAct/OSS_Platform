# DynReAct documentation instructions

## Prerequisites

Install mkdocs in the DynReAct virtual environment: navigate to [DynReActService](./DynReActService) and install:

```
pip install -r requirements_dev.txt
```

## Generate docs

* Update the service documentation: generate the new *openapi_dynreact.json* file (TODO explain) and replace the existing one in [docsSrc](./docsSrc).
* Navigate to the repo base folder and run 
    ```
    mkdocs build
    ```
  
    This will generate some files and folders within the *docs* folder.
* Update the sub modules. First navigate to [DynReActBase](./DynReActBase) and generate run:
    ```
    mkdocs build
    ```
    
    This will generate or update the *site* folder within *DynReActBase*. Copy this folder to *<repo_base>/docs* and rename it to *DynReActBase*. Repeat for the [ShortTermPlanning](./ShortTermPlanning) folder, this time renaming *site* to *ShortTermPlanning*.
* Commit the updated *docs* folder to the *gh-pages* branch of the repository. Check that the documentation has been generated correctly at https://dynreact.github.io/OSS_Platform/ (maybe wait a short moment until static site generation is done).    



