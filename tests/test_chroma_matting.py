import unittest
import numpy as np
from PIL import Image
from h3_character_studio import matting

class ChromaMattingTests(unittest.TestCase):
    def image(self):
        a=np.full((32,32,3),[255,2,252],np.uint8)
        a[6:26,6:26]=[240,220,180]
        a[12:16,12:16]=[38,3,42]  # Trapped dark key spill inside the silhouette.
        a[9:11,9:11]=[18,15,12]  # Genuine ink stays.
        return Image.fromarray(a)
    def test_neural_matte_cannot_retain_trapped_background(self):
        im=self.image();alpha=np.ones((32,32))
        with self.assertRaises(ValueError):matting.validate_foreground(im,alpha,np.asarray(im),key=[255,2,252])
        clean,report=matting.background_prior(im,alpha,protected_palette=[[240,220,180],[18,15,12]])
        self.assertEqual(clean[13,13],0);self.assertEqual(clean[9,9],1)
        self.assertGreater(report['removed_background_pixels'],0)
        matting.validate_foreground(im,clean,np.asarray(im),key=report['background_rgb'])
    def test_ambiguous_character_color_is_rejected(self):
        with self.assertRaises(ValueError):matting.background_prior(self.image(),np.ones((32,32)),protected_palette=[[180,40,180]])
    def test_white_background_is_not_silently_chroma_keyed(self):
        alpha=np.ones((32,32));im=Image.new('RGB',(32,32),'white')
        clean,report=matting.background_prior(im,alpha)
        np.testing.assert_array_equal(clean,alpha);self.assertFalse(report['background_prior_verified'])

    def test_raw_composite_recovery_removes_halo_and_preserves_opaque_art(self):
        image=np.full((32,32,3),[255,2,252],np.uint8)
        image[4:28,4:28]=[220,190,150]
        image[4:28,4]=[238,113,212] # Skin mixed with the known magenta key.
        alpha=np.zeros((32,32));alpha[4:28,4:28]=1;alpha[4:28,4]=.7
        foreground=image.astype(float)/255;foreground[4:28,4]=[.94,.50,.86]
        fg,a,_=matting.recover_chroma_edges(Image.fromarray(image),alpha,foreground,key=[255,2,252],palette=[[220,190,150],[20,15,12]])
        np.testing.assert_array_equal(np.rint(fg[8,8]*255).astype(int),[220,190,150])
        np.testing.assert_array_equal(np.rint(fg[8,4]*255).astype(int),[220,190,150])
        self.assertFalse(matting.key_pixels(fg,np.array([255,2,252])/255,saturation=.08)[8,4])

    def test_other_saturated_background_does_not_enable_magenta_prior(self):
        alpha=np.ones((32,32));im=Image.new('RGB',(32,32),(0,255,0))
        clean,report=matting.background_prior(im,alpha)
        np.testing.assert_array_equal(clean,alpha);self.assertFalse(report['background_prior_verified'])
