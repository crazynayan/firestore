# Google Firestore ORM

This is yet another attempt to create an ORM for Google Firestore Database. 
This one is relatively simple with not too many options to customize.
In fact, the entire source code is in one file firestore-ci.py.

## Features
1. Provide multi-thread interface to simulate async interaction with firestore.
2. A truncate feature to only create fields with non-default values in firestore.
3. A cascade feature: This will be removed in future release.

## How to use for Google Cloud Firestore?
1. Install firestore-ci `pip install firestore-ci`
2. Save the GCP service-account JSON key in your project folder & give it a name. For e.g. `google-cloud.json`
3. Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to the JSON file. 
For e.g., in Linux `export GOOGLE_APPLICATION_CREDENTIALS="google-cloud.json"`

## How to use with Firestore Emulator?
1. Install firestore-ci `pip install firestore-ci`
2. Start the Firestore Emulator.
3. Set up the environment variables `FIRESTORE_EMULATOR_HOST` with the ip address of the emulator and `FIRESTORE_EMULATOR_PROJECT_ID` with the project id that the emulator is using.


## How to use with Firestore Emulator?
1. Import `FirestoreDocument` from `firestore_ci` 
2. Make your object model using `FirestoreDocument` For e.g. `class User(FirestoreDocument)`
3. Override the `__init__()` method to add your fields
4. Outside the model, call the `init()` method of Firestore document. For e.g. `User.init()` 
5. Here is a sample `models.py` file
```python
from firestore_ci import FirestoreDocument

class User(FirestoreDocument):
    def __init__(self):
        super().__init__()
        self.name = str()
        self.email = str()

User.init()
```

## Test
The unit test cases for this package can be found [here](https://github.com/crazynayan/firestore-test). 
The test cases are self-explanatory and reviewing them will help understanding this package better.