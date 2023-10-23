import os
import json
import pickle
import random
import time
import itertools

import numpy as np
from PIL import Image
import skimage.io as io
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon, Rectangle
from torch.utils.data import Dataset
import webdataset as wds

from minigpt4.datasets.datasets.base_dataset import BaseDataset
from minigpt4.datasets.datasets.caption_datasets import CaptionDataset
import threading

# Global lock
lock = threading.Lock()

def sample_object_bbox(objects, bbox):

    
    
    zipped_list = list(zip(objects, bbox))

    # Shuffle the zipped list
    random.shuffle(zipped_list)

    interleaved_list = str([{'{},{}'.format(obj, bbox.strip())} for obj, bbox in zipped_list]).replace("'","").replace("[","").replace("]","")

    # interleaved_list = " "+interleaved_list
    # print(interleaved_list)
    return interleaved_list

def bbox_to_object(objects, bbox):

    index_sample = random.sample(range(len(objects)),1)[0]

    sample_object = str(objects[index_sample])
    sample_bbox = bbox[index_sample]
    # sample_center_point = center_point[index_sample]

    sample_bbox = r"{"+str(sample_bbox) + "}"
    return sample_bbox, sample_object

def object_to_bbox(objects, bbox, center_point):
    index_sample = random.sample(range(len(objects)),1)[0]

    sample_object = objects[index_sample]
    sample_bbox = bbox[index_sample]
    sample_center_point = center_point[index_sample]

    instruction = "what is object and the bounding box in the center coordinate of "+str(sample_center_point)+"? "
    answer = "{"+str(sample_object)+","+str(sample_bbox)+"}"



    return instruction, answer


class COCOBBOXDataset(BaseDataset):
    def __init__(self, vis_processor, text_processor, location):
        super().__init__(vis_processor=vis_processor, text_processor=text_processor)

        print("coco box dataset")
        self.inner_dataset = wds.DataPipeline(
            wds.ResampledShards(location),
            wds.tarfile_to_samples(handler=wds.warn_and_continue),
            wds.shuffle(1000, handler=wds.warn_and_continue),
            wds.decode("pilrgb", handler=wds.warn_and_continue),
            wds.to_tuple("jpg", "json", handler=wds.warn_and_continue),
            wds.map_tuple(self.vis_processor, handler=wds.warn_and_continue),
            wds.map(self.to_dict, handler=wds.warn_and_continue),
        )

    def to_dict(self, sample):
        objects = sample[1]["objects"]
        boxes = sample[1]["bbox"]
        caption = sample[1]["caption"]


        new_bboxes = []

        image_size = sample[0].shape[1]
        image_size = 100
        for index in range(len(boxes)):
            box = boxes[index]
            x1 = int(box[0]*image_size)
            y1 = int(box[1]*image_size)
            x2 = x1 + int(box[2]*image_size)
            y2 = y1 + int(box[3]*image_size)
            assert x1>=0 and x1<=image_size
            assert x2>=0 and x2<=image_size
            assert y1>=0 and y1<=image_size
            assert y2>=0 and y2<=image_size
            
            new_bbox = " <"+str(x1)+"><"+str(y1)+"><"+str(x2)+"><"+str(y2)+">"
            # new_bbox = " <"+str(x1)+"><"+str(y1)+"><"+str(x2)+"><"+str(y2)+">"
            new_bboxes.append(new_bbox)

        instruction = r"Given an image, identify the objects and their bounding boxes in the format of {object,x1 y1 x2 y2}. "
        instruction = "<Img><ImageHere></Img> {}".format(self.text_processor(instruction))

        answer = sample_object_bbox(objects, new_bboxes)

        # print("instruction",instruction)
        # print("answer", answer)

        return {
            "image": sample[0],
            "instruction_input": instruction,
            "answer": answer,
            "data_type": "bbox",
            "question_split": True
        }


class COCOBboxToObjectDataset(BaseDataset):
    def __init__(self, vis_processor, text_processor, location):
        super().__init__(vis_processor=vis_processor, text_processor=text_processor)


        self.inner_dataset = wds.DataPipeline(
            wds.ResampledShards(location),
            wds.tarfile_to_samples(handler=wds.warn_and_continue),
            wds.shuffle(1000, handler=wds.warn_and_continue),
            wds.decode("pilrgb", handler=wds.warn_and_continue),
            wds.to_tuple("jpg", "json", handler=wds.warn_and_continue),
            wds.map_tuple(self.vis_processor, handler=wds.warn_and_continue),
            wds.map(self.to_dict, handler=wds.warn_and_continue),
        )


        self.instruction_pool = [
            "<Img><ImageHere></Img> what object is in this bounding box location {} ",
            "<Img><ImageHere></Img> what object is in this location {} ",
            "<Img><ImageHere></Img> identify the object present at this location {} ",
            "<Img><ImageHere></Img> what is it in bounding box location{} ",
            "<Img><ImageHere></Img> describe this object in {} ",
            "<Img><ImageHere></Img> this {} is ",
            "<Img><ImageHere></Img> the object in {} is ",
            "<Img><ImageHere></Img> please tell me what is inside the bounding box position {} ",
            "<Img><ImageHere></Img> what can you find in the bounding box area at position {}? ",
            "<Img><ImageHere></Img> what is the object occupying this area {} ",
            "<Img><ImageHere></Img> could you identify the content within the bounding box located at {} ",
            ]

    def to_dict(self, sample):
            
        objects = sample[1]["objects"]
        boxes = sample[1]["bbox"]

        new_bboxes = []

        image_size = sample[0].shape[1]
        image_size=100
        for index in range(len(boxes)):
            box = boxes[index]
            x1 = int(box[0]*image_size)
            y1 = int(box[1]*image_size)
            x2 = x1 + int(box[2]*image_size)
            y2 = y1 + int(box[3]*image_size)
            assert x1>=0 and x1<=image_size
            assert x2>=0 and x2<=image_size
            assert y1>=0 and y1<=image_size
            assert y2>=0 and y2<=image_size
            
            new_bbox = "<"+str(x1)+"><"+str(y1)+"><"+str(x2)+"><"+str(y2)+">"
            new_bboxes.append(new_bbox)
        
        bbox, object = bbox_to_object(objects, new_bboxes)

        instruction = random.choice(self.instruction_pool).format(bbox)
        return {
            "image": sample[0],
            "instruction_input": instruction,
            "answer": self.text_processor(object),
            "data_type": "bbox",
            "question_split": True
        }



# class ReferCOCODataset(Dataset):
#     def __init__(self, vis_processor, text_processor, vis_root, ann_path, dataset='refcoco', splitBy='unc'):
#         """
#         vis_root (string): Root directory of images (e.g. coco/images/)
#         ann_root (string): directory to store the annotation file
#         """
#         self.vis_root = vis_root

#         self.vis_processor = vis_processor
#         self.text_processor = text_processor

#         self.refer = REFER(ann_path, vis_root, dataset, splitBy)
#         self.ref_ids = self.refer.getRefIds()


#         self.instruction_pool = [
#             "[refer] {}",
#             "[refer] give me the location of {}",
#             "[refer] where is {} ?",
#             "[refer] from this image, tell me the location of {}",
#             "[refer] the location of {} is",
#             "[refer] could you tell me the location for {} ?",
#             "[refer] where can I locate the {} ?",
#         ]


#     def __len__(self):
#         return len(self.ref_ids)

#     def preprocess(self, index):
#         ref_id = self.ref_ids[index]
#         ref = self.refer.loadRefs(ref_id)[0]

#         image_file = 'COCO_train2014_{:0>12}.jpg'.format(ref["image_id"])
#         image_path = os.path.join(self.vis_root, image_file)
#         image = Image.open(image_path).convert("RGB")
#         image_orig_size = image.size
#         image = self.vis_processor(image)
#         image_new_size = [image.shape[1], image.shape[2]]

#         image_new_size = [100,100]

#         sample_sentence = random.choice(ref['sentences'])['raw']

#         refer_sentence = self.text_processor(sample_sentence)


#         bbox = self.refer.getRefBox(ref['ref_id'])

#         bbox_to_save = bbox
#         image_id_to_save = ref["image_id"]
#         ref_id_to_save = ref_id

#         item = {"image":image_id_to_save,"bbox":bbox_to_save,"ref id":ref_id_to_save, "sentence":refer_sentence}


#         def save_to_file():
#             with lock:
#                 with open("/ibex/project/c2133/minigpt4_v2_dataset/refercoco_record/save.json", "r") as f:
#                     refer_json = json.load(f)
                
#                 if ref_id_to_save not in refer_json.keys():
#                     print(item)
#                     refer_json[ref_id_to_save] = item

#                     with open("/ibex/project/c2133/minigpt4_v2_dataset/refercoco_record/save.json", "w") as f:
#                         json.dump(refer_json, f)


#         save_to_file()
#         # with open("/ibex/project/c2133/minigpt4_v2_dataset/refercoco_record/save.json","r") as f:
#         # refer_json = json.load(open("/ibex/project/c2133/minigpt4_v2_dataset/refercoco_record/save.json"))
        
#         # if ref_id_to_save not in refer_json.keys():
#         #     print(item)
#         #     refer_json[ref_id_to_save] = item

#         #     with open("/ibex/project/c2133/minigpt4_v2_dataset/refercoco_record/save.json","w") as f:
#         #         json.dump(refer_json,f)







#         bbox = [
#             bbox[0] / image_orig_size[0] * image_new_size[0],
#             bbox[1] / image_orig_size[1] * image_new_size[1],
#             (bbox[0] + bbox[2]) / image_orig_size[0] * image_new_size[0],
#             (bbox[1] + bbox[3]) / image_orig_size[1] * image_new_size[1]
#         ]
#         bbox = [int(x) for x in bbox]
#         bbox = "{{<{}><{}><{}><{}>}}".format(*bbox)
#         return {
#             "image": image,
#             "refer_sentence": refer_sentence,
#             "bbox": bbox,
#             "image_id": ref['image_id'],
#         }

#     def __getitem__(self, index):
#         data = self.preprocess(index)
#         instruction = random.choice(self.instruction_pool).format(data['refer_sentence'])

#         instruction = "<Img><ImageHere></Img> {} ".format(instruction)

#         return {
#             "image": data['image'],
#             "instruction_input": instruction,
#             "answer": data['bbox'],
#             "image_id": data['image_id'],
#         }


# class InvReferCOCODataset(ReferCOCODataset):
#     def __init__(self, *args, **kwargs):
#         super(InvReferCOCODataset, self).__init__(*args, **kwargs)

#         self.instruction_pool = [
#             "[identify] {}",
#             "[identify] what object is in this location {}",
#             "[identify] identify the object present at this location {}",
#             "[identify] what is it in {}",
#             "[identify] describe this object in {}",
#             "[identify] this {} is",
#             "[identify] the object in {} is",
#             ]

#     def __getitem__(self, index):
#         data = self.preprocess(index)

#         instruction = random.choice(self.instruction_pool).format(data['bbox'])

#         instruction = "<Img><ImageHere></Img> {} ".format(instruction)
        
#         return {
#             "image": data['image'],
#             "instruction_input": instruction,
#             "answer": self.text_processor(data['refer_sentence']),
#             "image_id": data['image_id'],
#         }


class ReferCOCODataset(Dataset):
    def __init__(self, vis_processor, text_processor, vis_root, ann_path, dataset='refcoco', splitBy='unc'):
        """
        vis_root (string): Root directory of images (e.g. coco/images/)
        ann_root (string): directory to store the annotation file
        """
        self.vis_root = vis_root

        self.vis_processor = vis_processor
        self.text_processor = text_processor

        self.refer = REFER(ann_path, vis_root, dataset, splitBy)
        self.ref_ids = self.refer.getRefIds(split="train")

        print(dataset, len(self.ref_ids))

        self.instruction_pool = [
            "[refer] {}",
            "[refer] give me the location of {}",
            "[refer] where is {} ?",
            "[refer] from this image, tell me the location of {}",
            "[refer] the location of {} is",
            "[refer] could you tell me the location for {} ?",
            "[refer] where can I locate the {} ?",
        ]


    def __len__(self):
        return len(self.ref_ids)

    def preprocess(self, index):
        ref_id = self.ref_ids[index]
        ref = self.refer.loadRefs(ref_id)[0]

        image_file = 'COCO_train2014_{:0>12}.jpg'.format(ref["image_id"])
        image_path = os.path.join(self.vis_root, image_file)
        image = Image.open(image_path).convert("RGB")
        image_orig_size = image.size
        image = self.vis_processor(image)
        image_new_size = [image.shape[1], image.shape[2]]

        image_new_size = [100,100]

        sample_sentence = random.choice(ref['sentences'])['raw']
        refer_sentence = self.text_processor(sample_sentence)


        bbox = self.refer.getRefBox(ref['ref_id'])
        bbox = [
            bbox[0] / image_orig_size[0] * image_new_size[0],
            bbox[1] / image_orig_size[1] * image_new_size[1],
            (bbox[0] + bbox[2]) / image_orig_size[0] * image_new_size[0],
            (bbox[1] + bbox[3]) / image_orig_size[1] * image_new_size[1]
        ]
        bbox = [int(x) for x in bbox]
        bbox = "{{<{}><{}><{}><{}>}}".format(*bbox)
        return {
            "image": image,
            "refer_sentence": refer_sentence,
            "bbox": bbox,
            "image_id": ref['image_id'],
        }

    def __getitem__(self, index):
        data = self.preprocess(index)
        instruction = random.choice(self.instruction_pool).format(data['refer_sentence'])

        instruction = "<Img><ImageHere></Img> {} ".format(instruction)

        return {
            "image": data['image'],
            "instruction_input": instruction,
            "answer": data['bbox'],
            "image_id": data['image_id'],
        }


class InvReferCOCODataset(ReferCOCODataset):
    def __init__(self, *args, **kwargs):
        super(InvReferCOCODataset, self).__init__(*args, **kwargs)

        self.instruction_pool = [
            "[identify] {}",
            "[identify] what object is in this location {}",
            "[identify] identify the object present at this location {}",
            "[identify] what is it in {}",
            "[identify] describe this object in {}",
            "[identify] this {} is",
            "[identify] the object in {} is",
            ]

    def __getitem__(self, index):
        data = self.preprocess(index)

        instruction = random.choice(self.instruction_pool).format(data['bbox'])

        instruction = "<Img><ImageHere></Img> {} ".format(instruction)
        
        return {
            "image": data['image'],
            "instruction_input": instruction,
            "answer": self.text_processor(data['refer_sentence']),
            "image_id": data['image_id'],
        }


class REFER:
    def __init__(self, data_root, vis_root, dataset='refcoco', splitBy='unc'):
        # provide data_root folder which contains refclef, refcoco, refcoco+ and refcocog
        # also provide dataset name and splitBy information
        # e.g., dataset = 'refcoco', splitBy = 'unc'
        dataset = dataset.split('inv')[-1]  # inv dataset is stored in the same path as normal dataset
        print('loading dataset %s into memory...' % dataset)
        self.ann_dir = os.path.join(data_root, dataset)
        if dataset in ['refcoco', 'refcoco+', 'refcocog']:
            self.vis_root = vis_root
        elif dataset == 'refclef':
            raise 'No RefClef image data'
        else:
            raise 'No refer dataset is called [%s]' % dataset

        # load refs from data/dataset/refs(dataset).json
        tic = time.time()
        ref_file = os.path.join(self.ann_dir, 'refs(' + splitBy + ').p')
        self.data = {}
        self.data['dataset'] = dataset
        self.data['refs'] = pickle.load(open(ref_file, 'rb'))

        # load annotations from data/dataset/instances.json
        instances_file = os.path.join(self.ann_dir, 'instances.json')
        instances = json.load(open(instances_file, 'r'))
        self.data['images'] = instances['images']
        self.data['annotations'] = instances['annotations']
        self.data['categories'] = instances['categories']

        # create index
        self.createIndex()
        print('DONE (t=%.2fs)' % (time.time() - tic))

    def createIndex(self):
        # create sets of mapping
        # 1)  Refs: 	 	{ref_id: ref}
        # 2)  Anns: 	 	{ann_id: ann}
        # 3)  Imgs:		 	{image_id: image}
        # 4)  Cats: 	 	{category_id: category_name}
        # 5)  Sents:     	{sent_id: sent}
        # 6)  imgToRefs: 	{image_id: refs}
        # 7)  imgToAnns: 	{image_id: anns}
        # 8)  refToAnn:  	{ref_id: ann}
        # 9)  annToRef:  	{ann_id: ref}
        # 10) catToRefs: 	{category_id: refs}
        # 11) sentToRef: 	{sent_id: ref}
        # 12) sentToTokens: {sent_id: tokens}
        print('creating index...')
        # fetch info from instances
        Anns, Imgs, Cats, imgToAnns = {}, {}, {}, {}
        for ann in self.data['annotations']:
            Anns[ann['id']] = ann
            imgToAnns[ann['image_id']] = imgToAnns.get(ann['image_id'], []) + [ann]
        for img in self.data['images']:
            Imgs[img['id']] = img
        for cat in self.data['categories']:
            Cats[cat['id']] = cat['name']

        # fetch info from refs
        Refs, imgToRefs, refToAnn, annToRef, catToRefs = {}, {}, {}, {}, {}
        Sents, sentToRef, sentToTokens = {}, {}, {}
        for ref in self.data['refs']:
            # ids
            ref_id = ref['ref_id']
            ann_id = ref['ann_id']
            category_id = ref['category_id']
            image_id = ref['image_id']

            # add mapping related to ref
            Refs[ref_id] = ref
            imgToRefs[image_id] = imgToRefs.get(image_id, []) + [ref]
            catToRefs[category_id] = catToRefs.get(category_id, []) + [ref]
            refToAnn[ref_id] = Anns[ann_id]
            annToRef[ann_id] = ref

            # add mapping of sent
            for sent in ref['sentences']:
                Sents[sent['sent_id']] = sent
                sentToRef[sent['sent_id']] = ref
                sentToTokens[sent['sent_id']] = sent['tokens']

        # create class members
        self.Refs = Refs
        self.Anns = Anns
        self.Imgs = Imgs
        self.Cats = Cats
        self.Sents = Sents
        self.imgToRefs = imgToRefs
        self.imgToAnns = imgToAnns
        self.refToAnn = refToAnn
        self.annToRef = annToRef
        self.catToRefs = catToRefs
        self.sentToRef = sentToRef
        self.sentToTokens = sentToTokens
        print('index created.')

    def getRefIds(self, image_ids=[], cat_ids=[], ref_ids=[], split=''):
        image_ids = image_ids if type(image_ids) == list else [image_ids]
        cat_ids = cat_ids if type(cat_ids) == list else [cat_ids]
        ref_ids = ref_ids if type(ref_ids) == list else [ref_ids]

        if len(image_ids) == len(cat_ids) == len(ref_ids) == len(split) == 0:
            refs = self.data['refs']
        else:
            if not len(image_ids) == 0:
                refs = [self.imgToRefs[image_id] for image_id in image_ids]
            else:
                refs = self.data['refs']
            if not len(cat_ids) == 0:
                refs = [ref for ref in refs if ref['category_id'] in cat_ids]
            if not len(ref_ids) == 0:
                refs = [ref for ref in refs if ref['ref_id'] in ref_ids]
            if not len(split) == 0:
                if split in ['testA', 'testB', 'testC']:
                    refs = [ref for ref in refs if
                            split[-1] in ref['split']]  # we also consider testAB, testBC, ...
                elif split in ['testAB', 'testBC', 'testAC']:
                    refs = [ref for ref in refs if ref['split'] == split]  # rarely used I guess...
                elif split == 'test':
                    refs = [ref for ref in refs if 'test' in ref['split']]
                elif split == 'train' or split == 'val':
                    refs = [ref for ref in refs if ref['split'] == split]
                else:
                    raise 'No such split [%s]' % split
        ref_ids = [ref['ref_id'] for ref in refs]
        return ref_ids

    def getAnnIds(self, image_ids=[], cat_ids=[], ref_ids=[]):
        image_ids = image_ids if type(image_ids) == list else [image_ids]
        cat_ids = cat_ids if type(cat_ids) == list else [cat_ids]
        ref_ids = ref_ids if type(ref_ids) == list else [ref_ids]

        if len(image_ids) == len(cat_ids) == len(ref_ids) == 0:
            ann_ids = [ann['id'] for ann in self.data['annotations']]
        else:
            if not len(image_ids) == 0:
                lists = [self.imgToAnns[image_id] for image_id in image_ids if image_id in self.imgToAnns]  # list of [anns]
                anns = list(itertools.chain.from_iterable(lists))
            else:
                anns = self.data['annotations']
            if not len(cat_ids) == 0:
                anns = [ann for ann in anns if ann['category_id'] in cat_ids]
            ann_ids = [ann['id'] for ann in anns]
            if not len(ref_ids) == 0:
                ids = set(ann_ids).intersection(set([self.Refs[ref_id]['ann_id'] for ref_id in ref_ids]))
        return ann_ids

    def getImgIds(self, ref_ids=[]):
        ref_ids = ref_ids if type(ref_ids) == list else [ref_ids]

        if not len(ref_ids) == 0:
            image_ids = list(set([self.Refs[ref_id]['image_id'] for ref_id in ref_ids]))
        else:
            image_ids = self.Imgs.keys()
        return image_ids

    def getCatIds(self):
        return self.Cats.keys()

    def loadRefs(self, ref_ids=[]):
        if type(ref_ids) == list:
            return [self.Refs[ref_id] for ref_id in ref_ids]
        elif type(ref_ids) == int:
            return [self.Refs[ref_ids]]

    def loadAnns(self, ann_ids=[]):
        if type(ann_ids) == list:
            return [self.Anns[ann_id] for ann_id in ann_ids]
        elif type(ann_ids) == int:
            return [self.Anns[ann_ids]]

    def loadImgs(self, image_ids=[]):
        if type(image_ids) == list:
            return [self.Imgs[image_id] for image_id in image_ids]
        elif type(image_ids) == int:
            return [self.Imgs[image_ids]]

    def loadCats(self, cat_ids=[]):
        if type(cat_ids) == list:
            return [self.Cats[cat_id] for cat_id in cat_ids]
        elif type(cat_ids) == int:
            return [self.Cats[cat_ids]]

    def getRefBox(self, ref_id):
        ref = self.Refs[ref_id]
        ann = self.refToAnn[ref_id]
        return ann['bbox']  # [x, y, w, h]

    def showRef(self, ref, seg_box='box'):
        ax = plt.gca()
        # show image
        image = self.Imgs[ref['image_id']]
        I = io.imread(os.path.join(self.vis_root, image['file_name']))
        ax.imshow(I)
        # show refer expression
        for sid, sent in enumerate(ref['sentences']):
            print('%s. %s' % (sid + 1, sent['sent']))
        # show segmentations
        if seg_box == 'seg':
            ann_id = ref['ann_id']
            ann = self.Anns[ann_id]
            polygons = []
            color = []
            c = 'none'
            if type(ann['segmentation'][0]) == list:
                # polygon used for refcoco*
                for seg in ann['segmentation']:
                    poly = np.array(seg).reshape((len(seg) / 2, 2))
                    polygons.append(Polygon(poly, True, alpha=0.4))
                    color.append(c)
                p = PatchCollection(polygons, facecolors=color, edgecolors=(1, 1, 0, 0), linewidths=3, alpha=1)
                ax.add_collection(p)  # thick yellow polygon
                p = PatchCollection(polygons, facecolors=color, edgecolors=(1, 0, 0, 0), linewidths=1, alpha=1)
                ax.add_collection(p)  # thin red polygon
            else:
                # mask used for refclef
                raise NotImplementedError('RefClef is not downloaded')
        # show bounding-box
        elif seg_box == 'box':
            ann_id = ref['ann_id']
            ann = self.Anns[ann_id]
            bbox = self.getRefBox(ref['ref_id'])
            box_plot = Rectangle((bbox[0], bbox[1]), bbox[2], bbox[3], fill=False, edgecolor='green', linewidth=3)
            ax.add_patch(box_plot)
