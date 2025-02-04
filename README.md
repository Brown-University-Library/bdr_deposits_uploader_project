# purpose

This webapp will allow Library staff to configure a new BDR (Brown Digital Repository) deposits-upload url for students to be able to upload works to the BDR.

---

Technical note: this webapp is configured to auto-create a UserProfile record, automatically, whenever a new User record is created -- whether via code or via the admin.

To enable that:
- models.UserProfile() was created
- apps.py was added to the bdr_deposits_uploader_app -- specifically to load signals.py
- signals.py was added to trigger the UserProfile auto-creation.
- settings.py was updated to specify `bdr_deposits_uploader_app.apps.BdrDepositsUploaderAppConfig`, instead of just `bdr_deposits_uploader_app`

---

Testing!