"""
Dataset management utiliies.
A Dataset is assumed to consist of two main objects: a matrix X of training examples and (optionally) a matrix Y of ground truth labels. In both cases, rows are observations and columns are features. 
For audio source separation in time-frequency, the columns of X will typically be frequency bins. The matrix Y can be a hard or soft mask, or for other tasks it may be just a class label.
"""
import abc
import os.path
import json
import numpy as np
import matplotlib.pyplot as plt
from untwist.base import types
from untwist.base.exceptions import *


class DatasetBase:
    _metaclass__ = abc.ABCMeta
    
    @abc.abstractmethod
    def add(self, x, y = np.empty((0,0))):
         return NotImplemented
         
    @abc.abstractmethod
    def get_batch(self, index, size):
        return NotImplemented
        
    @abc.abstractmethod
    def save(self, basename):
        return NotImplemented

    @abc.abstractmethod        
    def load(self, basename):
        return NotImplemented

class Dataset(DatasetBase):
    def __init__(self, x_width, x_type, y_width = 0, y_type = types.int_):
        self.X = np.empty((0, x_width), x_type)
        self.Y = np.empty((0, y_width), y_type)

    def add(self, x, y = np.empty((0,0))):
        self.X = np.append(self.X, x, 0)
        self.Y = np.append(self.Y, y, 0)

    def shuffle(self):
        perm = np.random.permutation(self.X.shape[0])
        self.X = self.X[perm,:]
        self.Y = self.Y[perm,:]
    
    def standardize(self):
        self.X = self.standardize_points(self.X)

    def normalize(self):
        self.X = (self.X - np.amin(self.X, 0)) \
        / (np.amax(self.X, 0) - np.amin(self.X, 0))
                
    def get_batch(self, index, size):
        x = self.X[index * size:(index + 1) * size,:]
        y = self.Y[index * size:(index + 1) * size,:]
        return (x,y)

    def save(self, path):
        np.save(path + "/X.npy", self.X)
        np.save(path + "/Y.npy", self.Y)        
        
    def load(self, path):
        self.X = np.load(path + "/X.npy")
        self.Y = np.load(path + "/Y.npy")                        
    
    def normalize_points(self, x):
        return np.divide(x - np.amin(self.X, 0) ,
            np.amax(self.X, 0) - np.amin(self.X, 0), np.empty_like(x))

    def standardize_points(self, x):
        return np.divide(x - np.mean(self.X, 0) , 
            np.std(self.X, 0),  np.empty_like(x))
        

"""Memory mapped version using numpy memmap"""
class MMDataset(DatasetBase):
    
    def __init__(self, path, 
        x_width = 0, x_type = np.float, 
        y_width = 0, y_type = types.int_):
        
        if os.path.exists(path + "/dataset.json"):
            print "Using existing dataset in "+path
            self._load(path)
        else:
            if x_width == 0 : raise "X width must be specified for new dataset"
            self.X = np.memmap(path + "/X.npy", x_type, "w+", 0, (1, x_width))
            self.X.flush()
            if y_width > 0: 
                self.Y = np.memmap(path + "/Y.npy", y_type, "w+", 0, (1, y_width))        
                self.Y.flush()
            else: self.Y = None
            self.index = None
            self.nrows = 0
            self.running_mean = np.zeros((1, x_width), x_type)
            self.running_dev = np.zeros((1, x_width), x_type)
            self.running_max = np.zeros((1, x_width), x_type)
            self.running_min = np.zeros((1, x_width), x_type)
            self.path = path

    def load(self, path):
            metadata = json.loads(open(path + "/dataset.json").read())
            self.index = metdata["index"]
            x_shape = metdata["x_shape"]
            x_type = metdata["x_type"]
            y_shape = metdata["y_shape"]
            y_type = metdata["y_type"]
            self.nrows = x_shape[0]
            self.running_mean = metdata["running_mean"]
            self.running_dev = metdata["running_dev"]
            self.running_max = metdata["running_min"]
            self.running_min = metdata["running_max"]
            self.X =  np.memmap(self.path+"/X.npy", x_type, shape = x_shape)
            if y_shape[0] > 0:
                self.Y = np.memmap(self.path+"/Y.npy", y_type, shape = y_shape)                
            else: self.Y = None
            self.path = path
                    
    def save(self, filename):
        metdata = {
            index:self.index,            
            x_shape: self.X.shape,
            x_type: self.X.type,
            y_shape: self.Y.shape,
            y_type: self.Y.type,
            running_mean:self.running_mean,
            running_dev:self.running_dev, 
            running_max: self.running_max, 
            running_max: self.running_max,
        }        
        with open(self.path+"/dataset.json", "wt") as f: 
            f.write(json.dumps(metdata))
        self.X.flush()
        if self.Y is not None: self.Y.flush()
    
    def add(self, x, y = None):
        self.X =  np.memmap(
            self.path+"/X.npy", self.X.dtype, 
            shape = (self.nrows + x.shape[0] , x.shape[1])
        )
        self.X[self.nrows:self.nrows + x.shape[0],:] = x
            
        if y is not None: 
            if x.shape != y.shape: raise "x and y should have the same shape"
            self.Y = np.memmap(
                self.path+"/Y.npy", self.Y.dtype,
                shape = (self.nrows + y.shape[0] , y.shape[1])
            )
            self.Y[self.nrows:self.nrows + y.shape[0],:] = y
            
        delta = x - self.running_mean
        n = self.X.shape[0] + np.arange(x.shape[0]) + 1            
        self.running_dev += np.sum(delta * (x - self.running_mean), 0)
        self.running_mean += np.sum(delta / n[:, np.newaxis], 0)
        self.running_max  = np.amax(np.vstack((self.running_max, x)), 0)
        self.running_min  = np.amin(np.vstack((self.running_min, x)), 0)            
        self.nrows += x.shape[0]

    def shuffle(self):
        self.index = np.random.permutation(self.X.shape[0])        

    def normalize_points(self, x):
        return np.divide(x - self.running_min, (self.running_max - self.running_min), np.empty_like(x))

    def standardize_points(self, x):
        tmp = np.empty_like(self.running_dev)
        tmp = np.divide(self.running_dev, (self.X.shape[0]-1), tmp)
        std = np.sqrt(tmp)
        result = np.empty_like(x)
        result = np.divide(x - self.running_mean, std, result)
        return result
        
    def get_batch(self, index, size, normalization = 2):              
        if self.index is None: self.index = np.arange(self.X.shape[0])
        if index > self.X.shape[0] / size :
            raise Exception("requested index too large")
        x = self.X[self.index[index * size:(index + 1) * size],:]        
        y = self.Y[self.index[index * size:(index + 1) * size],:] \
            if self.Y is not None else None
        if normalization == 1: 
                #x = (x - self.running_min) / (self.running_max - self.running_min)
            x = self.normalize_points(x)
        elif normalization == 2: 
            x = self.standardize_points(x)
            #std = np.sqrt(self.running_dev/(self.X.shape[0]-1))
            #x = (x - self.running_mean) / std        
        return (x,y)
