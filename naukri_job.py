from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from collections import Counter
import re
import matplotlib.pyplot as plt
import pandas as pd
import os
from datetime import datetime

# Function to scrape Naukri job postings and extract skills
def scrape_naukri_jobs(keyword, num_pages):
    job_details = []

    # Set up options for the Chrome WebDriver
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-notifications")  # Disable notifications
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

    # Start a Selenium WebDriver with options
    driver = webdriver.Chrome(options=options)

    try:
        # Search URL for Naukri
        url = f'https://www.naukri.com/{keyword}-jobs'
        print(f"Opening URL: {url}")
        driver.get(url)
        time.sleep(3)  # Wait for initial page load
        
        # Print page title for debugging
        print(f"Current page title: {driver.title}")

        # Loop through the specified number of pages
        for page in range(1, num_pages + 1):
            print(f"\n--- Scraping page {page} of {num_pages} ---")
            
            # Wait for job listings to appear using multiple possible selectors
            # These are based on recent inspection of Naukri.com
            job_selectors = [
                "//div[contains(@class, 'srp-jobtuple')]",  # Modern Naukri layout
                "//div[contains(@class, 'jobTupleHeader')]",  # Alternate layout
                "//article[contains(@class, 'jobTuple')]"     # Another variation
            ]
            
            jobs_found = False
            for selector in job_selectors:
                try:
                    print(f"Trying to find jobs with selector: {selector}")
                    job_elements = driver.find_elements(By.XPATH, selector)
                    if job_elements:
                        print(f"Found {len(job_elements)} job listings!")
                        jobs_found = True
                        
                        # Process each job listing
                        for i, job_element in enumerate(job_elements):
                            try:
                                job_info = extract_job_info(job_element)
                                if job_info:
                                    job_details.append(job_info)
                                    print(f"Added job {len(job_details)}: {job_info['title']} at {job_info['company']}")
                            except Exception as e:
                                print(f"Error processing job {i+1}: {str(e)}")
                        break
                except Exception as e:
                    print(f"Error with selector {selector}: {str(e)}")
            
            if not jobs_found:
                # Fallback: try to extract text from the whole page
                print("Could not find structured job listings, extracting from page text")
                page_text = driver.find_element(By.TAG_NAME, 'body').text
                text_based_jobs = extract_jobs_from_text(page_text)
                if text_based_jobs:
                    job_details.extend(text_based_jobs)
                    print(f"Added {len(text_based_jobs)} jobs from text parsing")
                else:
                    print("No jobs could be extracted from page text")
            
            # Navigate to next page if needed
            if page < num_pages:
                next_clicked = click_next_page(driver)
                if not next_clicked:
                    print("Could not navigate to next page, stopping pagination")
                    break
                time.sleep(3)  # Wait for next page to load
    
    except Exception as e:
        print(f"Error during scraping: {str(e)}")
    
    finally:
        # Close the WebDriver when done
        driver.quit()
    
    return job_details

# Function to extract job information from a job element
def extract_job_info(job_element):
    job_info = {'title': None, 'company': None, 'description': '', 'skills': []}
    
    # Extract job title with different possible selectors
    title_selectors = [
        './/a[contains(@class, "title")]',
        './/a[contains(@class, "jobTitle")]',
        './/a[contains(@class, "jdTitle")]'
    ]
    
    for selector in title_selectors:
        try:
            title_element = job_element.find_element(By.XPATH, selector)
            job_info['title'] = title_element.text.strip()
            if job_info['title']:
                break
        except:
            continue
    
    # Extract company name
    company_selectors = [
        './/a[contains(@class, "companyName")]',
        './/a[contains(@class, "company")]',
        './/span[contains(@class, "subTitle")]',
        './/div[contains(@class, "companyInfo")]'
    ]
    
    for selector in company_selectors:
        try:
            company_element = job_element.find_element(By.XPATH, selector)
            job_info['company'] = company_element.text.strip()
            if job_info['company']:
                break
        except:
            continue
    
    # Extract job description
    # First try to get it from the current element
    try:
        job_info['description'] = job_element.text
    except:
        job_info['description'] = ""
    
    # If we have a title but no description, try to click on the job to get more details
    if job_info['title'] and not job_info['description']:
        try:
            title_element = job_element.find_element(By.XPATH, './/a[contains(@class, "title")]')
            title_element.click()
            time.sleep(2)
            
            # Try to get the description from the modal
            desc_selectors = [
                '//div[contains(@class, "dang-inner-html")]', 
                '//div[contains(@class, "job-desc")]'
            ]
            
            for selector in desc_selectors:
                try:
                    desc_element = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    job_info['description'] = desc_element.text
                    break
                except:
                    continue
        except:
            pass
    
    # Extract skills from the description
    if job_info['description']:
        job_info['skills'] = extract_skills(job_info['description'])
    
    return job_info if job_info['title'] else None

# Function to extract jobs from page text when structured extraction fails
def extract_jobs_from_text(page_text):
    job_info = []
    
    # Split the text into lines
    lines = page_text.split('\n')
    
    # Look for job titles and company names patterns
    job_title = None
    company_name = None
    job_description = ""
    collecting_description = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for common job title patterns related to data engineering
        if any(keyword in line.lower() for keyword in ['data engineer', 'data scientist', 'analytics engineer']):
            # If we were collecting a description, save the previous job
            if job_title and collecting_description:
                skills = extract_skills(job_description)
                job_info.append({
                    'title': job_title,
                    'company': company_name if company_name else "Unknown",
                    'description': job_description,
                    'skills': skills
                })
            
            # Start new job
            job_title = line
            company_name = None
            job_description = line + " "  # Start description with title
            collecting_description = True
            
        # Look for company names or continue collecting description
        elif collecting_description:
            # The line after the job title is often the company name
            if not company_name and len(line) < 50:  # Company names are usually short
                company_name = line
            job_description += line + " "
    
    # Add the last job if we were collecting one
    if job_title and collecting_description:
        skills = extract_skills(job_description)
        job_info.append({
            'title': job_title,
            'company': company_name if company_name else "Unknown",
            'description': job_description,
            'skills': skills
        })
    
    return job_info

# Function to navigate to the next page
def click_next_page(driver):
    # First scroll to the bottom to ensure navigation is visible
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    
    # Try different methods to find and click next page button
    next_selectors = [
        "//a[contains(text(), 'Next')]",
        "//a[contains(@class, 'fright')]",
        "//a[contains(@class, 'pagination-next')]",
        "//span[contains(text(), 'Next')]/parent::*",
        "//div[contains(@class, 'pagination')]//a[contains(@class, 'fright')]"
    ]
    
    for selector in next_selectors:
        try:
            next_button = driver.find_element(By.XPATH, selector)
            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(1)
            # Try JavaScript click which is more reliable than Selenium click
            driver.execute_script("arguments[0].click();", next_button)
            print(f"Clicked next page button with selector: {selector}")
            return True
        except Exception as e:
            print(f"Couldn't click with selector {selector}: {str(e)}")
            continue
    
    # Try clicking on the next page number
    try:
        # Find the currently active page number
        active_page_elements = driver.find_elements(By.XPATH, "//a[contains(@class, 'active') or contains(@class, 'selected')]")
        if active_page_elements:
            current_page_text = active_page_elements[0].text.strip()
            try:
                current_page = int(current_page_text)
                next_page = current_page + 1
                
                # Find and click the next page number
                next_page_button = driver.find_element(By.XPATH, f"//a[text()='{next_page}']")
                driver.execute_script("arguments[0].scrollIntoView(true);", next_page_button)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", next_page_button)
                print(f"Clicked page number {next_page}")
                return True
            except ValueError:
                print(f"Could not convert current page text '{current_page_text}' to integer")
    except Exception as e:
        print(f"Error clicking next page number: {str(e)}")
    
    # Try another approach - direct URL modification
    try:
        current_url = driver.current_url
        if "-" in current_url:
            # Check if there's already a page parameter
            if "page-" in current_url:
                parts = current_url.split("page-")
                before_page = parts[0]
                after_page = parts[1] if len(parts) > 1 else ""
                
                # Extract current page number
                if after_page:
                    current_page = int(after_page.split("-")[0])
                    next_page = current_page + 1
                    
                    # Construct new URL with incremented page number
                    new_url = f"{before_page}page-{next_page}"
                    if "-" in after_page:
                        new_url += "-" + "-".join(after_page.split("-")[1:])
                        
                    driver.get(new_url)
                    print(f"Navigated to next page via URL: {new_url}")
                    return True
            else:
                # No page parameter yet, add page-2
                new_url = current_url.rstrip("/") + "/page-2"
                driver.get(new_url)
                print(f"Navigated to page 2 via URL: {new_url}")
                return True
    except Exception as e:
        print(f"Error with URL-based navigation: {str(e)}")
    
    # Last resort - try to simulate pressing the right arrow key
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.RIGHT)
        print("Tried navigating with RIGHT arrow key")
        time.sleep(2)
        # Check if URL changed to verify if this worked
        return True
    except:
        pass
    
    print("All pagination methods failed")
    return False

# Function to extract skills from text
def extract_skills(text):
    if not text:
        return []
        
    # List of skills to look for, categorized
    skill_categories = {
    # Databases and Data Warehouses
    'Databases': [
        'PostgreSQL', 'Snowflake', 'Databricks', 'Redshift', 'BigQuery', 'MongoDB', 'MySQL', 
        'Cassandra', 'DynamoDB', 'HBase', 'Neo4j', 'Elasticsearch', 'Dremio', 'Delta Lake','NoSQL','HDFS','Redis','S3'
    ],
    
    # Streaming and Messaging Systems
    'Streaming': [
        'Kafka', 'Kinesis', 'PubSub', 'Pub/sub', 'Event Hub', 'RabbitMQ', 'Apache Pulsar'
    ],
    
    # Orchestration and Workflow Management
    'Orchestration': [
        'Airflow', 'dbt', 'NiFi', 'Luigi', 'Dagster', 'Prefect', 'Kubernetes','Control-M','ADF'
    ],
    
    # Data Integration and ETL Tools
    'Data_Integration': [
        'Fivetran', 'Stitch', 'Segment', 'Matillion', 'Alteryx', 'Informatica', 'Talend', 
        'AWS Glue', 'Azure Data Factory', 'Google Cloud Dataflow'
    ],
    
    # Data Governance and Security
    'Data_Governance_and_Security': [
        'Collibra', 'Denodo', 'Immuta', 'Apache Ranger', 'Privacera', 'Alation','Metadata Management','Data Catalog','Atlan'
    ],
    
    # Query Engines and Data Lake Tools
    'Query_Engines_and Data_Lake_Tools': [
        'Presto', 'Starburst', 'Trino', 'Apache Drill'
    ],
    
    # Visualization and BI Tools
    'Visualization_and_BI_Tools': [
        'PowerBI', 'Tableau', 'Looker', 'Qlik', 'Sisense', 'Superset'
    ],
    
    # Programming Languages
    'Programming_Languages': [
        'Python', 'SQL', 'PySpark', 'Java', 'Scala', 'Rust', 'C++','Unix','Shell'
    ],
    
    # Big Data Frameworks
    'Big_Data_Frameworks': [
        'Hadoop', 'Hive', 'Spark', 'Flink', 'Beam', 'Pig'
    ],
    
    # Cloud Platforms and Services
    'Cloud_Platforms_and_Services': [
        'AWS', 'Azure', 'GCP', 'EMR', 'Dataproc', 'Synapse', 'Lambda', 'Step Functions'
    ],
    
    # Machine Learning and AI Tools
    'Machine_Learning_and_AI_Tools': [
        'Machine Learning', 'AI', 'TensorFlow', 'PyTorch', 'Scikit-learn', 'MLflow', 'Kubeflow'
    ],
    
    # Data Concepts and Architectures
    'Data_Concepts_and_Architectures': [
        'ETL', 'ELT', 'Data Warehouse', 'Data Lake', 'Data Lakehouse', 'Big Data', 
        'Data Modeling', 'Dimensional Modeling', 'Data Governance', 'Data Quality', 
        'Data Lineage', 'Data Catalog', 'Data Mesh', 'Data Fabric', 'Serverless','Data Pipeline'
    ],
    
    # DevOps and CI/CD Tools
    'DevOps_and_CI/CD_Tools': [
        'Docker', 'Kubernetes', 'Terraform', 'Jenkins', 'Git', 'GitHub Actions', 'CI/CD','Bitbucket','SVN'
    ],
    
    # Soft Skills and Methodologies
    'Soft_Skills_and_Methodologies': [
        'Agile', 'Scrum', 'DevOps', 'Problem Solving', 'Collaboration', 'Documentation','Jira'
    ]
    ,'Concepts': ['Big Data', 'Machine Learning', 'AI', 'Data Modeling', 'Data Pipeline','ETL','ELT','ML','Data Warehouse','Unix','OLAP','OLTP']
}

    # Flatten the categories into a list of skills with their categories
    skills_with_categories = []
    for category, category_skills in skill_categories.items():
        for skill in category_skills:
            skills_with_categories.append((skill, category))

    # Extract skills from text with their categories
    text = text.lower()
    found_skills = []
    for skill, category in skills_with_categories:
        if skill.lower() in text:
            found_skills.append((skill, category))
    
    # Extract just the skill names for the original function behavior
    skills_list = [skill for skill, _ in found_skills]
    
    return skills_list, found_skills

# Function to generate visualizations
def generate_skill_visualizations(skill_counts, total_jobs, search_keyword):
    
    # Create output directory if it doesn't exist
    output_dir = 'skill_analysis'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Convert to DataFrame for easier plotting
    df = pd.DataFrame(skill_counts.most_common(25), columns=['Skill', 'Count'])
    df['Percentage'] = df['Count'] / total_jobs * 100
    
    # Create a horizontal bar chart for the top 25 skills
    plt.figure(figsize=(14, 12))
    bars = plt.barh(df['Skill'], df['Count'], color='skyblue')
    plt.xlabel('Number of Job Listings')
    plt.ylabel('Skills')
    plt.title(f'Top 25 Skills for {search_keyword.replace("-", " ").title()} Jobs on Naukri.com')
    
    # Add count labels to the bars
    for bar in bars:
        width = bar.get_width()
        plt.text(width + 0.3, bar.get_y() + bar.get_height()/2, f'{width:.0f}', 
                 ha='left', va='center')
    
    plt.tight_layout()
    bar_chart_path = f"{output_dir}/data_engineer_skills_bar_chart.png"
    plt.savefig(bar_chart_path)
    print(f"Bar chart saved to: {bar_chart_path}")
    
    # Create a pie chart for the top 10 skills
    plt.figure(figsize=(12, 10))
    top10_df = df.head(10)
    plt.pie(top10_df['Percentage'], labels=top10_df['Skill'], autopct='%1.1f%%', 
            startangle=90, shadow=True, explode=[0.05]*len(top10_df))
    plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
    plt.title(f'Top 10 Skills Distribution for {search_keyword.replace("-", " ").title()} Jobs')
    
    pie_chart_path = f"{output_dir}/data_engineer_skills_pie_chart.png"
    plt.savefig(pie_chart_path)
    print(f"Pie chart saved to: {pie_chart_path}")
    
    # Also save the data to CSV
    csv_path = f"{output_dir}/data_engineer_skills_data.csv"
    full_df = pd.DataFrame(skill_counts.most_common(), columns=['Skill', 'Count'])
    full_df['Percentage'] = full_df['Count'] / total_jobs * 100
    full_df.to_csv(csv_path, index=False)
    print(f"Skills data saved to: {csv_path}")
    
    return bar_chart_path, pie_chart_path, csv_path

# Function to generate category-based visualizations
def generate_category_visualizations(skills_with_categories, total_jobs, search_keyword):
    search_keyword = "data-engineer"
    output_dir = 'skill_analysis'
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Convert to DataFrame and group by category
    df = pd.DataFrame(skills_with_categories, columns=['Skill', 'Category', 'Count'])
    category_counts = df.groupby('Category')['Count'].sum().reset_index()
    category_counts = category_counts.sort_values('Count', ascending=False)
    
    # Calculate percentages
    category_counts['Percentage'] = category_counts['Count'] / total_jobs * 100
    
    # Create a bar chart for categories
    plt.figure(figsize=(14, 10))
    bars = plt.barh(category_counts['Category'], category_counts['Count'], color='lightgreen')
    plt.xlabel('Number of Job Listings')
    plt.ylabel('Skill Categories')
    plt.title(f'Skill Categories for {search_keyword.replace("-", " ").title()} Jobs on Naukri.com')
    
    # Add count labels
    for bar in bars:
        width = bar.get_width()
        plt.text(width + 0.3, bar.get_y() + bar.get_height()/2, f'{width:.0f}', 
                 ha='left', va='center')
    
    plt.tight_layout()
    category_chart_path = f"{output_dir}/data_engineer_categories_chart.png"
    plt.savefig(category_chart_path)
    print(f"Category chart saved to: {category_chart_path}")
    
    # Create a pie chart for categories
    plt.figure(figsize=(12, 10))
    plt.pie(category_counts['Percentage'], labels=category_counts['Category'], autopct='%1.1f%%', 
            startangle=90, shadow=True, explode=[0.03]*len(category_counts))
    plt.axis('equal')
    plt.title(f'Skill Category Distribution for {search_keyword.replace("-", " ").title()} Jobs')
    
    category_pie_path = f"{output_dir}/data_engineer_categories_pie.png"
    plt.savefig(category_pie_path)
    print(f"Category pie chart saved to: {category_pie_path}")
    
    # Create individual charts for each category
    for category in df['Category'].unique():
        category_skills = df[df['Category'] == category].sort_values('Count', ascending=False)
        if len(category_skills) > 0:
            plt.figure(figsize=(12, 8))
            bars = plt.barh(category_skills['Skill'], category_skills['Count'], color='orange')
            plt.xlabel('Number of Job Listings')
            plt.ylabel('Skills')
            plt.title(f'{category} Skills for {search_keyword.replace("-", " ").title()} Jobs')
            
            # Add count labels
            for bar in bars:
                width = bar.get_width()
                plt.text(width + 0.3, bar.get_y() + bar.get_height()/2, f'{width:.0f}', 
                         ha='left', va='center')
            
            plt.tight_layout()
            # Fix the path issue by replacing slashes with underscores in category name
            category_filename = category.lower().replace(' ', '_').replace('/', '_')
            skill_category_path = f"{output_dir}/data_engineer_{category_filename}_skills.png"
            plt.savefig(skill_category_path)
            print(f"{category} skills chart saved to: {skill_category_path}")
    
    # Save category data to CSV
    csv_path = f"{output_dir}/data_engineer_categories_data.csv"
    category_counts.to_csv(csv_path, index=False)
    print(f"Category data saved to: {csv_path}")
    
    # Save detailed skills by category to CSV
    detailed_csv_path = f"{output_dir}/data_engineer_skills_by_category.csv"
    df.to_csv(detailed_csv_path, index=False)
    print(f"Detailed skills by category saved to: {detailed_csv_path}")
    
    return category_chart_path, category_pie_path

# Function to generate mock data for demonstration
def generate_mock_data():
    print("Generating mock data for demonstration...")
    
    mock_skills = [
        # Database skills
        ('SQL', 'Databases', 95),
        ('PostgreSQL', 'Databases', 65),
        ('MySQL', 'Databases', 55),
        ('MongoDB', 'Databases', 30),
        ('Snowflake', 'Databases', 58),
        ('BigQuery', 'Databases', 42),
        ('Redshift', 'Databases', 38),
        
        # Processing skills
        ('Spark', 'Processing', 85),
        ('Hadoop', 'Processing', 45),
        ('Databricks', 'Processing', 62),
        ('Pyspark', 'Processing', 75),
        ('EMR', 'Processing', 25),
        ('Hive', 'Processing', 35),
        
        # Cloud skills
        ('AWS', 'Cloud', 89),
        ('Azure', 'Cloud', 72),
        ('GCP', 'Cloud', 48),
        ('S3', 'Cloud', 40),
        
        # Programming languages
        ('Python', 'Programming', 98),
        ('Java', 'Programming', 45),
        ('Scala', 'Programming', 30),
        ('R', 'Programming', 25),
        
        # Streaming
        ('Kafka', 'Streaming', 60),
        ('Kinesis', 'Streaming', 30),
        ('PubSub', 'Streaming', 20),
        
        # ETL/ELT
        ('ETL', 'ETL/ELT', 78),
        ('ELT', 'ETL/ELT', 65),
        ('Airflow', 'Orchestration', 70),
        ('dbt', 'Data Modeling', 48),
        ('Informatica', 'ETL/ELT', 35),
        ('Talend', 'ETL/ELT', 28),
        
        # Visualization
        ('Tableau', 'Visualization', 55),
        ('PowerBI', 'Visualization', 50),
        ('Looker', 'Visualization', 30),
        
        # Concepts
        ('Big Data', 'Concepts', 75),
        ('Data Warehouse', 'Concepts', 68),
        ('Machine Learning', 'Concepts', 45),
        ('AI', 'Concepts', 35)
    ]
    
    # Calculate all skills (just the skill names)
    all_skills = [skill for skill, _, _ in mock_skills]
    
    # Create job skill data
    job_details = []
    total_jobs = 100
    
    # Create Counter for skills
    skill_counts = Counter()
    for skill, _, count in mock_skills:
        skill_counts[skill] = count
    
    return job_details, all_skills, mock_skills, skill_counts, total_jobs

# Main function
if __name__ == "__main__":
    #keyword = "data-engineer-jobs-in-kolkata?k=data%20engineer&l=kolkata&experience=3&nignbevent_src=jobsearchDeskGNB"
    keyword = "data-engineer-jobs-in-india-data-engineer?k=data%20engineer&l=india%20data%20engineer&experience=3&nignbevent_src=jobsearchDeskGNB"  # Using Naukri URL format
    num_pages = 100  # Number of pages to scrape
    
    print(f"Searching for '{keyword}' jobs on Naukri.com")
    try:
        job_details = scrape_naukri_jobs(keyword, num_pages)
        
        print(f'\nTotal data engineer jobs analyzed: {len(job_details)}')
        
        if job_details:
            # Collect all skills with their categories
            all_skills = []
            all_skills_with_categories = []
            
            for job in job_details:
                # We need to extract skills again to get categories
                skills_text = job.get('description', '')
                if skills_text:
                    skills_only, skills_with_cats = extract_skills(skills_text)
                    all_skills.extend(skills_only)
                    all_skills_with_categories.extend(skills_with_cats)
            
            if all_skills:
                skill_counts = Counter(all_skills)
                top_skills = skill_counts.most_common(25)
    
                print("\nTop 10 skills for Data Engineers:")
                for skill, count in top_skills:
                    print(f'{skill}: {count}')
                
                # Print percentage of jobs requiring each skill
                print("\nPercentage of jobs requiring each skill:")
                total_jobs = len(job_details)
                for skill, count in top_skills:
                    percentage = (count / total_jobs) * 100
                    print(f'{skill}: {percentage:.1f}%')
                    
                # Process the skills with categories
                category_skills_with_count = []
                for skill, category in all_skills_with_categories:
                    category_skills_with_count.append((skill, category, all_skills.count(skill)))
                
                # Generate visualizations
                generate_visualizations = True
            else:
                print("No skills were found in the job descriptions")
                generate_visualizations = False
        else:
            print("No jobs were found or analyzed")
            generate_visualizations = False
            
        # If real scraping failed or had no results, use mock data
        if not generate_visualizations:
            print("\nUsing sample data to demonstrate visualizations")
            _, all_skills, category_skills_with_count, skill_counts, total_jobs = generate_mock_data()
            generate_visualizations = True
            
        # Generate and save visualizations
        if generate_visualizations:
            print("\nGenerating visualizations...")
            bar_chart, pie_chart, csv_file = generate_skill_visualizations(skill_counts, total_jobs, keyword)
            
            # Generate category visualizations
            print("\nGenerating category-based visualizations...")
            category_chart, category_pie = generate_category_visualizations(category_skills_with_count, total_jobs, keyword)
            
            print(f"\nAnalysis complete! Visual reports have been saved to the 'skill_analysis' directory.")
            print(f"- Bar chart: {bar_chart}")
            print(f"- Pie chart: {pie_chart}")
            print(f"- CSV data: {csv_file}")
            print(f"- Category chart: {category_chart}")
            print(f"- Category pie chart: {category_pie}")
    
    except Exception as e:
        print(f"An error occurred during execution: {str(e)}")
        print("\nUsing sample data to demonstrate visualizations instead")
        job_details, all_skills, category_skills_with_count, skill_counts, total_jobs = generate_mock_data()
            
        # Generate and save visualizations
        print("\nGenerating visualizations...")
        bar_chart, pie_chart, csv_file = generate_skill_visualizations(skill_counts, total_jobs, keyword)
        
        # Generate category visualizations
        print("\nGenerating category-based visualizations...")
        category_chart, category_pie = generate_category_visualizations(category_skills_with_count, total_jobs, keyword)
        
        print(f"\nAnalysis complete! Visual reports have been saved to the 'skill_analysis' directory.")
        print(f"- Bar chart: {bar_chart}")
        print(f"- Pie chart: {pie_chart}")
        print(f"- CSV data: {csv_file}")
        print(f"- Category chart: {category_chart}")
        print(f"- Category pie chart: {category_pie}") 