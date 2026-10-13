import unittest,tempfile
from pathlib import Path
import numpy as np
from h3_character_studio import materials,core,normals
class MaterialOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.color=np.full((256,256,4),255,np.uint8)
        self.shapes=[dict(id='hand',kind='plane',points=[[0,0],[255,0],[255,255],[0,255]],normal=[.2,0,1]),dict(id='cuff',kind='ellipsoid',ellipse=[120,130,20,20],metallic=True)]
    def tearDown(self):self.temp.cleanup()
    def write(self,**updates):
        data=dict(schema_version=1,frame=0,source_sha256='source',review_status='agent-reviewed',reviewed_by='fixture',regions={'cuff':[[120,130]]},protected_regions={'skin':[[121,130]]});data.update(updates);core.write_json(self.root/'00000.json',data)
    def test_transported_silver_without_annotation_is_rejected(self):
        with self.assertRaises(ValueError):materials.constrain(self.shapes,self.color,'source',0,None)
    def test_annotation_cannot_overwrite_skin(self):
        self.write(regions={'cuff':[[121,130]]})
        with self.assertRaises(ValueError):materials.constrain(self.shapes,self.color,'source',0,self.root)
    def test_stale_or_unreviewed_annotations_are_rejected(self):
        self.write(source_sha256='old')
        with self.assertRaises(ValueError):materials.constrain(self.shapes,self.color,'source',0,self.root)
        self.write(review_status='proposal')
        with self.assertRaises(ValueError):materials.constrain(self.shapes,self.color,'source',0,self.root)
    def test_material_vector_cannot_expand_beyond_owned_pixel(self):
        self.write();shapes,_=materials.constrain(self.shapes,self.color,'source',0,self.root)
        actual,_,metal=normals.render(self.color,shapes);base,_,_=normals.render(self.color,self.shapes[:1])
        self.assertEqual(int(metal.sum()),1);np.testing.assert_array_equal(actual[~metal],base[~metal])
    def test_face_ownership_cannot_flood_neck_or_cloth(self):
        shapes=[dict(id='cloth',kind='plane',points=[[0,0],[255,0],[255,255],[0,255]],normal=[-.2,0,1]),dict(id='face',kind='plane',points=[[0,0],[255,0],[255,255],[0,255]],normal=[.14,0,1])]
        self.write(regions={},surface_regions={'face':[[130,70]]})
        approved,_=materials.constrain(shapes,self.color,'source',0,self.root)
        actual,_,_=normals.render(self.color,approved);base,_,_=normals.render(self.color,shapes[:1]);mask=materials.pixels([[130,70]])
        np.testing.assert_array_equal(actual[~mask],base[~mask])
        self.write(regions={})
        with self.assertRaises(ValueError):materials.constrain(shapes,self.color,'source',0,self.root)
