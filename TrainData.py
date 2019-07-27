'''
Created on 20 Feb 2017

@author: jkiesele
'''

from __future__ import print_function

from Weighter import Weighter
from pdb import set_trace
import os
import time
import numpy
import logging
import tempfile
import copy
import shutil
import threading
import multiprocessing

threadingfileandmem_lock=threading.Lock()
#threadingfileandmem_lock.release()
#multiproc_fileandmem_lock=multiprocessing.Lock()

def fileTimeOut(fileName, timeOut):
    '''
    simple wait function in case the file system has a glitch.
    waits until the dir, the file should be stored in/read from, is accessible
    again, or the the timeout
    '''
    filepath=os.path.dirname(fileName)
    if len(filepath) < 1:
        filepath = '.'
    if os.path.isdir(filepath):
        return

    counter=0
    print('file I/O problems... waiting for filesystem to become available for '+fileName)
    while not os.path.isdir(filepath):
        if counter > timeOut:
            print('...file could not be opened within '+str(timeOut)+ ' seconds')
        counter+=1
        time.sleep(1)


def _read_arrs_(arrwl,arrxl,arryl,arrzl,doneVal,fileprefix,tdref=None,randomSeed=None):
    import gc
    gc.collect()

    import h5py
    from sklearn.utils import shuffle
    try:
        idstrs=['w','x','y','z']
        h5f = h5py.File(fileprefix,'r')
        alllists=[arrwl,arrxl,arryl,arrzl]
        for j in range(len(idstrs)):
            fidstr=idstrs[j]
            arl=alllists[j]
            for i in range(len(arl)):
                idstr=fidstr+str(i)
                h5f[idstr].read_direct(arl[i])
                #shuffle each read-in, but each array with the same seed (keeps right asso)
                if randomSeed:
                    arl[i]=shuffle(arl[i], random_state=randomSeed)
                
        doneVal.value=True
        h5f.close()
        del h5f
    except Exception as d:
        raise d
    finally:
        if tdref:
            tdref.removeRamDiskFile()  
    
    
class ShowProgress(object):
    def __init__(self,nsteps,total):
        self.nsteps=nsteps
        self.total=total
        self._stepvec=[]
        for i in range(nsteps):
            self._stepvec.append(float(i+1)*float(total)/float(nsteps))
            
        self._counter=0
        
    def show(self,index):
        if index==0:
            logging.info('0%')
        if index>self._stepvec[self._counter]:
            logging.info(str(int(float(index)/float(self.total)*100))+'%')
            self._counter=self._counter+1
        
    def reset(self):
        self._counter=0
        



class TrainData(object):
    '''
    Base class for batch-wise training of the DNN
    '''
    
    
    
    
    def __init__(self):
        '''
        Constructor
        
        '''
        
        self.treename=""
        self.undefTruth=[]  
        self.referenceclass=''
        self.truthclasses=[]
        self.allbranchestoberead=[]
        
        self.weightbranchX=''
        self.weightbranchY=''
        self.weight_binX = numpy.array([-1e12, 1e12],dtype=float)
        self.weight_binY = numpy.array([-1e12, 1e12],dtype=float)
        
        self.reducedtruthclasses=[]
        self.regressiontargetclasses=[]
        
        self.flatbranches=[]
        self.branches=[]
        self.branchcutoffs=[]
                
        self.readthread=None
        self.readdone=None
        
        self.remove=True    
        self.weight=False
        self.ignore_when_weighting=[] #for use with referenceclass='lowest'
        self.removeUnderOverflow=False
        
        self.clear()
        
        self.reduceTruth(None)
        
    def __del__(self):
        self.readIn_abort()
        self.clear()
        

    def clear(self):
        self.samplename=''
        self.readIn_abort()
        self.readthread=None
        self.readdone=None
        if hasattr(self, 'x'):
            del self.x
            del self.y
            del self.z
            del self.w
        if hasattr(self, 'w_list'):
            del self.w_list
            del self.x_list
            del self.y_list
            del self.z_list
            
        self.x=[numpy.array([])]
        self.y=[numpy.array([])]
        self.z=[numpy.array([])]
        self.w=[numpy.array([])]
        
        self.nsamples=None
        
    def skim(self, event=0):
        xs=[]
        ys=[]
        ws=[]
        
        for x in self.x:
            xs.append(x[event:event+1,...])
        for y in self.y:
            ys.append(y[event:event+1,...])
        for w in self.w:
            ws.append(w[event:event+1,...])
        self.clear()
        self.nsamples=1
        self.x=xs
        self.y=ys
        self.w=ws 
    
    def defineCustomPredictionLabels(self, labels):
        self.customlabels=labels
        
    def getInputShapes(self):
        '''
        returns a list for each input shape. In most cases only one entry
        '''
        outl=[]
        for x in self.x:
            outl.append(x.shape)
        shapes=[]
        for s in outl:
            _sl=[]
            for i in range(len(s)):
                if i:
                    _sl.append(s[i])
            s=(_sl)
            if len(s)==0:
                s.append(1)
            shapes.append(s)
            
        if hasattr(self,'generatePerBatch') and self.generatePerBatch:
            shapes.append([len(self.generatePerBatch)])
            
        return shapes
        
    def getTruthShapes(self):
        outl=[len(self.getUsedTruth())]
        return outl
    
    
    def getNRegressionTargets(self):
        if not self.regressiontargetclasses:
            return 0
        return len(self.regressiontargetclasses)
    
    def getNClassificationTargets(self):
        return len(self.getUsedTruth())
        
    def addBranches(self, blist, cutoff=1):
        self.branches.append(blist)
        self.registerBranches(blist)
        self.branchcutoffs.append(cutoff)
        
    def registerBranches(self,blist):
        self.allbranchestoberead.extend(blist)
        
    def getUsedTruth(self):
        if len(self.reducedtruthclasses) > 0:
            return self.reducedtruthclasses
        else:
            return self.truthclasses
    

    def reduceTruth(self, tuple_in=None):
        self.reducedtruthclasses=self.truthclasses
        if tuple_in is not None:
            return numpy.array(tuple_in.tolist())

    def writeOut(self,fileprefix):
        
        import h5py
        
        #this is a workaround because hdf5 files written on eos are unreadable...
        final_output_file=fileprefix

        # with h5py >= 2.9 you can directly write to an open tempfile, but for now
        # we'd need to use tempfile as a safe name generator
        #with tempfile.NamedTemporaryFile(suffix='.meta', delete=False) as t:
        #    h5f = h5py.File(t)
        
        t = tempfile.NamedTemporaryFile(suffix='.meta', delete=False)
        t.close()

        h5f = h5py.File(t.name, 'w')
        
        # try "lzf", too, faster, but less compression
        def _writeoutListinfo(arrlist,fidstr,h5F):
            arr=numpy.array([len(arrlist)])
            h5F.create_dataset(fidstr+'_listlength',data=arr)
            for i in range(len(arrlist)):
                idstr=fidstr+str(i)
                h5F.create_dataset(idstr+'_shape',data=arrlist[i].shape)
            
        def _writeoutArrays(arrlist,fidstr,h5F):    
            for i in range(len(arrlist)):
                idstr=fidstr+str(i)
                arr=arrlist[i]
                from DeepJetCore.compiled.c_readArrThreaded import writeArray
                if arr.dtype!='float32':
                    arr=arr.astype('float32')
                writeArray(arr.ctypes.data,final_output_file[:-4]+fidstr+'.'+str(i),list(arr.shape))
        
        arr=numpy.array([self.nsamples],dtype='int')
        h5f.create_dataset('n', data=arr)
        
        _writeoutListinfo(self.w,'w',h5f)
        _writeoutListinfo(self.x,'x',h5f)
        _writeoutListinfo(self.y,'y',h5f)
        _writeoutListinfo(self.z,'z',h5f)
        
        _writeoutArrays(self.w,'w',h5f)
        _writeoutArrays(self.x,'x',h5f)
        _writeoutArrays(self.y,'y',h5f)
        _writeoutArrays(self.z,'z',h5f)
        
        h5f.close()
            
        shutil.copyfile(t.name, final_output_file)
       
    def __createArr(self,shapeinfo):
        import ctypes

        fulldim=1
        for d in shapeinfo:
            fulldim*=d 
        if fulldim < 0: #catch some weird things that happen when there is a file IO error
            fulldim=0 
        # reserve memory for array
        shared_array_base = multiprocessing.RawArray(ctypes.c_float, int(fulldim))
        shared_array = numpy.ctypeslib.as_array(shared_array_base)#.get_obj())
        #print('giving shape',shapeinfo)
        shared_array = shared_array.reshape(shapeinfo)
        #print('gave shape',shapeinfo)
        return shared_array
    
    def removeRamDiskFile(self):
        if hasattr(self, 'ramdiskfile'):
            try:
                if self.ramdiskfile and os.path.exists(self.ramdiskfile):
                    if "meta" in self.ramdiskfile[-4:]:
                        os.system('rm -f '+self.ramdiskfile[:-4]+"*")
                    else:
                        os.remove(self.ramdiskfile)
            except OSError:
                pass
            self.ramdiskfile=None
               
    def readIn_async(self,fileprefix,read_async=True,shapesOnly=False,ramdiskpath='',randomseed=None):
        
        if self.readthread and read_async:
            print('\nTrainData::readIn_async: started new read before old was finished. Intended? Waiting for first to finish...\n')
            self.readIn_join()
            
        #print('read')
        
        import h5py
        
        #print('\ninit async read\n')
        
        fileTimeOut(fileprefix,120)
        #print('\nfile access ok\n')
        self.samplename=fileprefix
        
        
        
        def _readListInfo_(idstr):
            sharedlist=[]
            shapeinfos=[]
            wlistlength=self.h5f[idstr+'_listlength'][0]
            #print(idstr,'list length',wlistlength)
            for i in range(wlistlength):
                sharedlist.append(numpy.array([]))
                iidstr=idstr+str(i)
                shapeinfo=numpy.array(self.h5f[iidstr+'_shape'])
                shapeinfos.append(shapeinfo)
            return sharedlist, shapeinfos
        
        
        with threadingfileandmem_lock:
            try:
                self.h5f = h5py.File(fileprefix,'r')
            except:
                raise IOError('File %s could not be opened properly, it may be corrupted' % fileprefix)
            self.nsamples=self.h5f['n']
            self.nsamples=self.nsamples[0]
            if True or not hasattr(self, 'w_shapes'):
                self.w_list,self.w_shapes=_readListInfo_('w')
                self.x_list,self.x_shapes=_readListInfo_('x')
                self.y_list,self.y_shapes=_readListInfo_('y')
                self.z_list,self.z_shapes=_readListInfo_('z')
            else:
                print('\nshape known\n')
                self.w_list,_=_readListInfo_('w')
                self.x_list,_=_readListInfo_('x')
                self.y_list,_=_readListInfo_('y')
                self.z_list,_=_readListInfo_('z')
                
            self.h5f.close()
            del self.h5f
            self.h5f=None
            if shapesOnly:
                return
            
            readfile=fileprefix
            
            isRamDisk=len(ramdiskpath)>0
            if isRamDisk:
                import uuid
                unique_filename=''
                
                unique_filename = ramdiskpath+'/'+str(uuid.uuid4())+'.z'
                if "meta" in readfile[-4:]:
                    filebase=readfile[:-4]
                    unique_filename = ramdiskpath+'/'+str(uuid.uuid4())
                    shutil.copyfile(filebase+'meta',unique_filename+'.meta')
                    for i in range(len(self.w_list)):
                        shutil.copyfile(filebase+'w.'+str(i),unique_filename+'.w.'+str(i))
                    for i in range(len(self.x_list)):
                        shutil.copyfile(filebase+'x.'+str(i),unique_filename+'.x.'+str(i))
                    for i in range(len(self.y_list)):
                        shutil.copyfile(filebase+'y.'+str(i),unique_filename+'.y.'+str(i))
                    for i in range(len(self.z_list)):
                        shutil.copyfile(filebase+'z.'+str(i),unique_filename+'.z.'+str(i))
                    unique_filename+='.meta'
                        
                else:
                    unique_filename = ramdiskpath+'/'+str(uuid.uuid4())+'.z'
                    shutil.copyfile(fileprefix, unique_filename)
                readfile=unique_filename
                self.ramdiskfile=readfile

            #create shared mem in sync mode
            for i in range(len(self.w_list)):
                self.w_list[i]=self.__createArr(self.w_shapes[i])
                
            for i in range(len(self.x_list)):
                self.x_list[i]=self.__createArr(self.x_shapes[i])
                
            for i in range(len(self.y_list)):
                self.y_list[i]=self.__createArr(self.y_shapes[i])
            for i in range(len(self.z_list)):
                self.z_list[i]=self.__createArr(self.z_shapes[i])
            
            if read_async:
                self.readdone=multiprocessing.Value('b',False)
                        
        if read_async:
            if "meta" in readfile[-4:]:
                #new format
                from DeepJetCore.compiled.c_readArrThreaded import startReading
                self.readthreadids=[]
                filebase=readfile[:-4]
                for i in range(len(self.w_list)):
                    self.readthreadids.append(startReading(self.w_list[i].ctypes.data,
                                                           filebase+'w.'+str(i),
                                                           fileprefix,
                                                           list(self.w_list[i].shape),
                                                           isRamDisk))
                for i in range(len(self.x_list)):
                    self.readthreadids.append(startReading(self.x_list[i].ctypes.data,
                                                           filebase+'x.'+str(i),
                                                           fileprefix,
                                                           list(self.x_list[i].shape),
                                                           isRamDisk))
                for i in range(len(self.y_list)):
                    self.readthreadids.append(startReading(self.y_list[i].ctypes.data,
                                                           filebase+'y.'+str(i),
                                                           fileprefix,
                                                           list(self.y_list[i].shape),
                                                           isRamDisk))

                for i in range(len(self.z_list)):
                    self.readthreadids.append(startReading(self.z_list[i].ctypes.data,
                                                           filebase+'z.'+str(i),
                                                           list(self.z_list[i].shape),
                                                           isRamDisk))  
                
            else:
                self.readthread=multiprocessing.Process(target=_read_arrs_, 
                                                        args=(self.w_list,
                                                              self.x_list,
                                                              self.y_list,
                                                              self.z_list,
                                                              self.readdone,
                                                              readfile,
                                                              self,randomseed))
                self.readthread.start()
        else:
            if "meta" in readfile[-4:]:
                from DeepJetCore.compiled.c_readArrThreaded import readBlocking
                filebase=readfile[:-4]
                self.readthreadids=[]
                for i in range(len(self.w_list)):
                    (readBlocking(self.w_list[i].ctypes.data,
                                                           filebase+'w.'+str(i),
                                                           fileprefix,
                                                           list(self.w_list[i].shape),
                                                           isRamDisk))
                for i in range(len(self.x_list)):
                    (readBlocking(self.x_list[i].ctypes.data,
                                                           filebase+'x.'+str(i),
                                                           fileprefix,
                                                           list(self.x_list[i].shape),
                                                           isRamDisk))
                for i in range(len(self.y_list)):
                    (readBlocking(self.y_list[i].ctypes.data,
                                                           filebase+'y.'+str(i),
                                                           fileprefix,
                                                           list(self.y_list[i].shape),
                                                           isRamDisk))
                for i in range(len(self.z_list)):
                    (readBlocking(self.z_list[i].ctypes.data,
                                                           filebase+'z.'+str(i),
                                                           list(self.z_list[i].shape),
                                                           isRamDisk))
                
            else:
                self.readdone=multiprocessing.Value('b',False)
                _read_arrs_(self.w_list,self.x_list,self.y_list,self.z_list,self.readdone,readfile,self,randomseed)
            
            
        
    def readIn_abort(self):
        self.removeRamDiskFile()
        if not self.readthread:
            return
        self.readthread.terminate()
        self.readthread=None
        self.readdone=None
     
    def readIn_join(self,wasasync=True,waitforStart=True):
        
        try:
            if not not hasattr(self, 'readthreadids') and not waitforStart and not self.readthread and wasasync:
                print('\nreadIn_join:read never started\n')
            
            if waitforStart:
                while (not hasattr(self, 'readthreadids')) and not self.readthread:
                    time.sleep(0.1)
                if hasattr(self, 'readthreadids'):
                    while not self.readthreadids:
                        time.sleep(0.1)
            
            counter=0
            
            if hasattr(self, 'readthreadids') and self.readthreadids:
                from DeepJetCore.compiled.c_readArrThreaded import isDone
                doneids=[]
                while True:
                    for id in self.readthreadids:
                        if id in doneids: continue
                        if isDone(id):
                            doneids.append(id)
                    if len(self.readthreadids) == len(doneids):
                        break
                    time.sleep(0.1)
                    counter+=1
                    if counter>3000: #read failed. do synchronous read, safety option if threads died
                        print('\nfalling back to sync read\n')
                        self.readthread.terminate()
                        self.readthread=None
                        self.readIn(self.samplename)
                        return
                
            else: #will be removed at some point
                while wasasync and (not self.readdone or not self.readdone.value): 
                    if not self.readthread:
                        time.sleep(.1)
                        continue
                    self.readthread.join(.1)
                    counter+=1
                    if counter>3000: #read failed. do synchronous read, safety option if threads died
                        print('\nfalling back to sync read\n')
                        self.readthread.terminate()
                        self.readthread=None
                        self.readIn(self.samplename)
                        return
                if self.readdone.value:
                    self.readthread.join(.1)
                    
            #move away from shared memory
            #this costs performance but seems necessary
            direct=False
            with threadingfileandmem_lock:
                if direct:
                    self.w=self.w_list
                    self.x=self.x_list
                    self.y=self.y_list
                    self.z=self.z_list
                else:
                    self.w=copy.deepcopy(self.w_list)
                    self.x=copy.deepcopy(self.x_list)
                    self.y=copy.deepcopy(self.y_list)
                    self.z=copy.deepcopy(self.z_list)
                    
                del self.w_list
                del self.x_list
                del self.y_list
                del self.z_list
            #in case of some errors during read-in
            
        except Exception as d:
            raise d
        finally:
            self.removeRamDiskFile()
        
        #check if this is really neccessary 
        def reshape_fast(arr,shapeinfo):
            if len(shapeinfo)<2:
                shapeinfo=numpy.array([arr.shape[0],1])
            arr=arr.reshape(shapeinfo)
            return arr
        
        
        for i in range(len(self.w)):
            self.w[i]=reshape_fast(self.w[i],self.w_shapes[i])
        for i in range(len(self.x)):
            self.x[i]=reshape_fast(self.x[i],self.x_shapes[i])
        for i in range(len(self.y)):
            self.y[i]=reshape_fast(self.y[i],self.y_shapes[i])
        for i in range(len(self.z)):
            self.z[i]=reshape_fast(self.z[i],self.z_shapes[i])
        
        self.w_list=None
        self.x_list=None
        self.y_list=None
        self.z_list=None
        if wasasync and self.readthread:
            self.readthread.terminate()
        self.readthread=None
        self.readdone=None
        
    def readIn(self,fileprefix,shapesOnly=False):
        self.readIn_async(fileprefix,False,shapesOnly)
        direct=True
        if direct:
            self.w=self.w_list
            self.x=self.x_list
            self.y=self.y_list
            self.z=self.z_list
        else:
            self.w=copy.deepcopy(self.w_list)
            del self.w_list
            self.x=copy.deepcopy(self.x_list)
            del self.x_list
            self.y=copy.deepcopy(self.y_list)
            del self.y_list
            self.z=copy.deepcopy(self.z_list)
            del self.z_list
        
        def reshape_fast(arr,shapeinfo):
            if len(shapeinfo)<2:
                shapeinfo=numpy.array([arr.shape[0],1])
            if shapesOnly:
                arr=numpy.zeros(shape=shapeinfo)
            else:
                arr=arr.reshape(shapeinfo)
            return arr
        
        
            
            
        for i in range(len(self.w)):
            self.w[i]=reshape_fast(self.w[i],self.w_shapes[i])
        for i in range(len(self.x)):
            self.x[i]=reshape_fast(self.x[i],self.x_shapes[i])
        for i in range(len(self.y)):
            self.y[i]=reshape_fast(self.y[i],self.y_shapes[i])
        for i in range(len(self.z)):
            self.z[i]=reshape_fast(self.z[i],self.z_shapes[i])
            
        self.w_list=None
        self.x_list=None
        self.y_list=None
        self.z_list=None
        self.readthread=None
        
        
    def readTreeFromRootToTuple(self, filenames, limit=None, branches=None):
        '''
        To be used to get the initial tupel for further processing in inherting classes
        Makes sure the number of entries is properly set
        
        can also read a list of files (e.g. to produce weights/removes from larger statistics
        (not fully tested, yet)
        '''
        if  branches==None:
            branches=self.allbranchestoberead
            
        if branches is None or len(branches) == 0:
            return numpy.array([],dtype='float32')
            
        #print(branches)
        #remove duplicates
        usebranches=list(set(branches))
        tmpbb=[]
        for b in usebranches:
            if len(b):
                tmpbb.append(b)
        usebranches=tmpbb
            
        import ROOT
        from root_numpy import tree2array, root2array
        if isinstance(filenames, list):
            for f in filenames:
                fileTimeOut(f,120)
            print('add files')
            nparray = root2array(
                filenames, 
                treename = self.treename, 
                stop = limit,
                branches = usebranches
                )
            print('done add files')
            return nparray
            print('add files')
        else:    
            fileTimeOut(filenames,120) #give eos a minute to recover
            rfile = ROOT.TFile.Open(filenames)
            tree = rfile.Get(self.treename)
            if not self.nsamples:
                self.nsamples=tree.GetEntries()
            nparray = tree2array(tree, stop=limit, branches=usebranches)
            return nparray
        
    def read_truthclasses(self,filename):
        npy_array = self.readTreeFromRootToTuple(filename)
        arl=[]
        for c in self.truthclasses:
            a = numpy.asarray(npy_array[c])
            a = a.reshape((a.shape[0],1))
            arl.append(a)
            
        return numpy.concatenate(arl,axis=-1)
        
    def make_means(self, nparray):
        from preprocessing import meanNormProd
        return meanNormProd(nparray)
        
    def produceMeansFromRootFile(self,filename, limit=500000):
        from preprocessing import meanNormProd
        nparray = self.readTreeFromRootToTuple(filename, limit=limit)
        means = numpy.array([],dtype='float32')
        if len(nparray):
            means = self.make_means(nparray)
        
        del nparray
        return means
    
    #overload if necessary
    def make_empty_weighter(self):
        weighter = Weighter() 
        weighter.undefTruth = self.undefTruth
        weighter.removeUnderOverflow = self.removeUnderOverflow
        weighter.ignore_when_weighting = self.ignore_when_weighting
        
        if self.remove or self.weight:
            weighter.setBinningAndClasses(
                [self.weight_binX,self.weight_binY],
                self.weightbranchX,self.weightbranchY,
                self.reducedtruthclasses
                )
        return weighter

       
    def produceBinWeighter(self,filenames):
        weighter = self.make_empty_weighter()
        branches = [self.weightbranchX,self.weightbranchY]
        #branches.extend(self.truthclasses)
        showprog=ShowProgress(5,len(filenames))
        counter=0
        if self.remove or self.weight:
            for fname in filenames:
                # Read truths 
                truth_array = self.readTreeFromRootToTuple(fname, branches=self.truthclasses)
                # Use defined reduced truths
                reduced_array = self.reduceTruth(truth_array)
                dtype = zip(self.reducedtruthclasses, [col.dtype for col in reduced_array.transpose()])
                reduced_array = reduced_array.ravel().view(dtype)		
                # Read variables to weight along
                weight_along_array = self.readTreeFromRootToTuple(fname, branches=branches)
                # Merge two arrays
                import numpy.lib.recfunctions as rfn
                nparray = rfn.merge_arrays([reduced_array, weight_along_array],  flatten = True, usemask = False)

               	weighter.addDistributions(nparray, referenceclass=self.referenceclass) 
                del nparray
                del truth_array
                del weight_along_array
                del reduced_array
            

                showprog.show(counter)
                counter=counter+1
            weighter.createRemoveProbabilitiesAndWeights(self.referenceclass)
        return weighter
    
        
    

    def _normalize_input_(self, weighter, npy_array, oversample=1):
        weights = None
        if self.weight:
            weights=weighter.getJetWeights(npy_array)
            self.w = [weights for _ in self.y]
        elif self.remove:
            x_in=self.x
            y_in=self.y
            z_in=self.z
            for i in range(oversample):
                notremoves=weighter.createNotRemoveIndices(npy_array)
                if self.undefTruth:
                    undef=npy_array[self.undefTruth].sum(axis=1)
                    notremoves-=undef
                print(' to created remove indices', i)
                weights=notremoves
                
                print('remove', i)
                if not i:
                    self.x = [x[notremoves > 0] for x in x_in]
                    self.y = [y[notremoves > 0] for y in y_in]
                    self.z = [z[notremoves > 0] for z in z_in]
                else:
                    self.x = [self.x[i].concatenate(x_in[i][notremoves > 0]) for i in range(len(self.x))]
                    self.y = [self.y[i].concatenate(y_in[i][notremoves > 0]) for i in range(len(self.y))]
                    self.z = [self.z[i].concatenate(z_in[i][notremoves > 0]) for i in range(len(self.z))]
            self.w = [numpy.zeros(self.x[0].shape)+1 for _ in self.y]
                    
                
            newnsamp=self.x[0].shape[0]
            print('reduced content to ', int(float(newnsamp)/float(self.nsamples)*100),'%')
            self.nsamples = newnsamp
        else:
            print('neither remove nor weight')
            weights=numpy.empty(self.nsamples)
            weights.fill(1.)
            self.w = [weights for _ in self.y]        

        

