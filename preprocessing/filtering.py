'''
Newton Kwan
April 12, 2019
Velma

This file reads a parquet file from S3, filters out empty abstracts, and filters out lower quality abstracts 
'''

import pyspark
from pyspark.sql.types import *
from pyspark.sql.functions import udf, struct, col, rank
from pyspark.sql import SQLContext
from pyspark import SparkContext
from pyspark.sql.session import SparkSession
import boto3

sc = SparkContext.getOrCreate()
spark = SparkSession(sc)

orig_bucket_name = "open-research-corpus"

def get_id(line):
    parenthesis = "\"" # string literal for "
    paper_id_tag = "\"id\"" # find the first occurence of "id"
    id_label_start = line.find(paper_id_tag) # this is the index that the id label starts
    id_tag_start = id_label_start + 6 # this is the index that the id tag starts. Always be 6.
    id_tag_end = line.find(parenthesis, id_tag_start)  #this is the index that the id tag ends
    id_tag = line[id_tag_start:id_tag_end] # id tag string 
    return id_tag

def get_title(line):
    # look for the title of the paper and return the tag 
    paper_title_tag = "\"title\""
    parenthesis = "\"" # string literal for "
    
    title_label_start = line.find(paper_title_tag) # index for the title label start 
    title_tag_start = title_label_start + 9
    title_tag_end = line.find(parenthesis+",\"", title_tag_start) 
    title_tag = line[title_tag_start:title_tag_end]
    '''
    if title_tag[-1] == ".":
        title_tag = title_tag.replace(".", "")
    if title_tag[-1] == "]":
        title_tag = title_tag.replace("]", "")
        title_tag = title_tag.replace("[", "")
    if "\\\"" in title_tag:
        title_tag = title_tag.replace("\\\"", "\"")
    '''
    return title_tag

def get_abstract(line):
    '''
    this function looks for the abstract tag of the paper
    '''
    paper_abstract_tag = "\"paperAbstract\""
    parenthesis = "\"" # string literal for "
    
    abstract_label_start = line.find(paper_abstract_tag) # index that the abstrat label starts
    abstract_tag_start = abstract_label_start + 17 # the start of the abstract tag 
    abstract_tag_end = line.find(parenthesis, abstract_tag_start) # the end of the abstract tag 
    abstract_tag = line[abstract_tag_start:abstract_tag_end] # abstract tag string
    if r"\n" in abstract_tag:
        abstract_tag = abstract_tag.replace(r"\n", " ")
    return abstract_tag

def get_citation(line):
    '''
    Get the citation from the values 
    '''
    paper_citation_tag = "\"inCitations\"" # find the occurence of "inCitations"
    bracket = r"]" # look for "]"
    
    citation_label_start = line.find(paper_citation_tag) # index that the citation label starts  
    citation_tag_start = citation_label_start + 15 # index that the citation tag starts
    citation_tag_end = line.find(bracket, citation_tag_start)  # this is the index that the citation tag ends 
    if citation_tag_start == citation_tag_end: # if there are no citations: 
        num_citations = 0
        citation_list = []
    else:
        citation_list = line[citation_tag_start:citation_tag_end].split(",") # make it a list, count number of entries
        num_citations = len(citation_list) # number of citations 
    return num_citations

def get_tag(line):
    '''
    Extracts the tag from the value column in the dataframe 
    '''
    paper_entities_tag = "\"entities\""
    bracket = r"]" # look for "]"
    
    entities_label_start = line.find(paper_entities_tag) # index for the title label start 
    entities_tag_start = entities_label_start + 12
    entities_tag_end = line.find(bracket+",\"", entities_tag_start) 
    entities_tag = line[entities_tag_start:entities_tag_end]
    if "\"" in entities_tag:
        entities_tag = entities_tag.replace("\"", "")
    return entities_tag  

def adding_ids(df):
    '''
    This function takes the raw data dataframe and adds on an id column for the data
    Ex: 
    value        id 
    laeinaelk    23402939423
    lakeflake    02398402384
    ieifniena    23402938402
    '''
    add_ids = df.withColumn("id", get_id_udf(df.value))
    return add_ids

def adding_titles(df):
    '''
    This function takes the raw data dataframe and adds on an id column for the data
    Ex: 
    value        id             title 
    laeinaelk    23402939423    "Mastering the game of Go"
    lakeflake    02398402384    "Computer Science is fun!"
    ieifniena    23402938402    "Who knows what to do????"
    '''
    add_titles = df.withColumn("title", get_title_udf(df.value))
    return add_titles

def adding_abstracts(df):
    '''
    This function takes the raw + id dataframe and adds on abstracts column for the data
    Ex
    value        id             title                         abstracts 
    laeinaelk    23402939423    "Mastering the game of Go"    Mastering the game of ...
    lakeflake    02398402384    "Computer Science is fun!"    When people go outside...
    ieifniena    23402938402    "Who knows what to do????"    Data engineers love to...
    '''
    add_abstracts = df.withColumn("abstracts", get_abstract_udf(df.value))
    return add_abstracts

def adding_citations(df):
    '''
    This function takes the raw data dataframe and adds on a citation column for the data
    Ex
    value        id             title                         abstracts                  citations
    laeinaelk    23402939423    "Mastering the game of Go"    Mastering the game of ...  18
    lakeflake    02398402384    "Computer Science is fun!"    When people go outside...  2
    ieifniena    23402938402    "Who knows what to do????"    Data engineers love to...  102
     '''
    add_citations = df.withColumn("citations", get_citation_udf(df.value))
    return add_citations

def adding_tags(df):
    '''
    This function takes the raw data dataframe and adds on a citation column for the data
    Ex
    value        id             title                         abstracts                  citations   tags
    laeinaelk    23402939423    "Mastering the game of Go"    Mastering the game of ...  18          "CS", "Game"
    lakeflake    02398402384    "Computer Science is fun!"    When people go outside...  2           "World", "Tree"
    ieifniena    23402938402    "Who knows what to do????"    Data engineers love to...  102         "DE", "Spark"
     '''
    add_tags = df.withColumn("tags", get_tag_udf(df.value))
    return add_tags 

def drop_values(df):
    '''
    This function takes the dataframe and drops the value column
    Ex
    id             title                         abstracts                  citations   tags
    23402939423    "Mastering the game of Go"    Mastering the game of ...  18          "CS", "Game"
    02398402384    "Computer Science is fun!"    When people go outside...  2           "World", "Tree"
    23402938402    "Who knows what to do????"    Data engineers love to...  102         "DE", "Spark"
    '''
    return df.drop(df.value)

def drop_empty_rows(df):
    df_filtered = df.filter(df.abstracts != "")
    return df_filtered

def filter_by_citation(df):
    df_filtered = df.filter(df.citations > 10)
    return df_filtered

# create a user defined function for get_id and get_abstract, which is compatable with a spark dataframe 
get_id_udf = udf(lambda line: get_id(line), StringType())
get_abstract_udf = udf(lambda line: get_abstract(line), StringType())
get_title_udf = udf(lambda line: get_title(line), StringType())
get_citation_udf = udf(lambda line:get_citation(line), StringType())
get_tag_udf = udf(lambda line:get_tag(line), StringType())

def clean_df(df):
    '''
    cleans the dataframe using the defined above functions 
    '''
    df = adding_citations(df)
    df = filter_by_citation(df)
    df = adding_abstracts(df)
    df = drop_empty_rows(df)
    df = adding_ids(df)
    df = adding_titles(df)
    df = adding_tags(df)
    df = drop_values(df)
    return df

def read_and_store_files(bucket_name, filename):
    '''
    This function reads all of the .gz files from S3 
    and returns a pyspark dataframe with all of the rows from 
    the files it has read in
    '''
    
    # reads files from an S3 bucket 
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    
    # initialize a dataframe 
    
    # for each additional piece of data, add the rows to the current df 
    df_init_switch = False # turns true when the first df has been initialized
    num_rows = 0 # counts the current number of rows 
    for parquet_file in bucket.objects.filter(Prefix="corpus"):
        '''
        if "part" in gz_file.key:
            print(gz_file.key)
            df = spark.read.text("s3a://{0}/{1}".format(bucket_name, gz_file.key))
            df = clean_df(df)
        '''
        # used earlier but the file is too big 
        #df = spark.read.text("s3a://{0}/{1}".format(bucket_name, gz_file.key))
        #store_in_s3(df, gz_file.key)
        if "part" in parquet_file.key:
            print(parquet_file.key)
            df = spark.read.parquet("s3a://{0}/{1}".format(bucket_name, parquet_file.key))
            df = clean_df(df) # clean the dataframe 
            df = df.coalesce(1)
            store_in_s3(df, filename)

    return 1

def store_in_s3(df, filename):
    '''
    This file takes a dataframe and appends it into existing dataframe that is in S3 
    '''
    df.write.save("s3a://preprocessed-open-research-corpus/{0}".format(filename), format="parquet", mode="append")
    
    return 1

def read_from_s3():
	'''
	This function reads a parquet file from an S3 bucket 
	'''
	df = spark.read.load("s3a://preprocessed-open-research-corpus/filtered-dataframes/part-*")
	return df


filename = "filtered-dataframes"
#df = read_from_s3()
#df = clean_df(df)
#df = df.coalesce(1)
#store_in_s3(df, filename)
#bucket_name = "preprocessed-open-research-corpus"
#read_and_store_files(bucket_name, filename)
df = read_from_s3()
print("Number of rows", df.count())

print("Schema for filtered data")
print("-------------------------------------")
df.createOrReplaceTempView("filtered_df")
df.printSchema()
results = spark.sql("SELECT * FROM filtered_df")
print("Entries for filtered_df")
print("----------------------------")
results.show()















